//! Kopiert einen Ausschnitt aus einem Swapchain-Bild (GPU) in den RAM.
//!
//! Das Spiel rendert in Bilder ("Swapchain-Images"), die es dann an die
//! Runtime übergibt. Kurz bevor die Runtime das Bild bekommt (in xrEndFrame),
//! hängen wir einen kleinen Kopier-Befehl an die GPU-Warteschlange des
//! Spiels und warten, bis er fertig ist. Das kostet nur beim Foto ein paar ms.

use ash::vk;
use ash::vk::Handle;

pub struct VkCtx {
    _entry: ash::Entry, // muss am Leben bleiben (hält libvulkan geladen)
    instance: ash::Instance,
    physical_device: vk::PhysicalDevice,
    device: ash::Device,
    queue: vk::Queue,
    pool: vk::CommandPool,
}

impl VkCtx {
    /// Baut den Vulkan-Kontext aus den Handles, die das Spiel bei
    /// xrCreateSession übergeben hat.
    ///
    /// UNSAFE: Die rohen Zeiger müssen gültige Vulkan-Objekte des Spiels sein.
    /// Das garantiert die OpenXR-Spezifikation, solange die Session lebt.
    pub unsafe fn new(
        instance: usize,
        physical_device: usize,
        device: usize,
        queue_family: u32,
        queue_index: u32,
    ) -> Result<Self, String> {
        let entry = ash::Entry::load().map_err(|e| format!("libvulkan nicht ladbar: {e}"))?;
        let instance = ash::Instance::load(entry.static_fn(), vk::Instance::from_raw(instance as u64));
        let device = ash::Device::load(instance.fp_v1_0(), vk::Device::from_raw(device as u64));
        let queue = device.get_device_queue(queue_family, queue_index);
        let pool = device
            .create_command_pool(
                &vk::CommandPoolCreateInfo::default()
                    .queue_family_index(queue_family)
                    .flags(vk::CommandPoolCreateFlags::TRANSIENT | vk::CommandPoolCreateFlags::RESET_COMMAND_BUFFER),
                None,
            )
            .map_err(|e| format!("vkCreateCommandPool: {e}"))?;
        Ok(Self {
            _entry: entry,
            instance,
            physical_device: vk::PhysicalDevice::from_raw(physical_device as u64),
            device,
            queue,
            pool,
        })
    }

    fn find_memory(&self, bits: u32, flags: vk::MemoryPropertyFlags) -> Option<u32> {
        let props = unsafe { self.instance.get_physical_device_memory_properties(self.physical_device) };
        (0..props.memory_type_count).find(|&i| {
            bits & (1 << i) != 0 && props.memory_types[i as usize].property_flags.contains(flags)
        })
    }

    /// Kopiert Rechteck (x, y, w, h) aus Ebene `layer` des Bildes.
    /// Ergebnis: w*h*4 Bytes. Nur für 4-Byte-Formate (RGBA8/BGRA8)!
    ///
    /// UNSAFE: `image` muss ein gültiges Swapchain-Bild sein, das gerade
    /// vom Spiel freigegeben wurde (Layout COLOR_ATTACHMENT_OPTIMAL).
    pub unsafe fn copy_region(
        &self,
        image: vk::Image,
        layer: u32,
        (x, y, w, h): (i32, i32, u32, u32),
    ) -> Result<Vec<u8>, String> {
        let d = &self.device;
        let size = (w as u64) * (h as u64) * 4;

        // 1) Puffer im RAM-sichtbaren Speicher anlegen
        let buffer = d
            .create_buffer(
                &vk::BufferCreateInfo::default()
                    .size(size)
                    .usage(vk::BufferUsageFlags::TRANSFER_DST)
                    .sharing_mode(vk::SharingMode::EXCLUSIVE),
                None,
            )
            .map_err(|e| format!("vkCreateBuffer: {e}"))?;
        let req = d.get_buffer_memory_requirements(buffer);
        let Some(mem_type) = self.find_memory(
            req.memory_type_bits,
            vk::MemoryPropertyFlags::HOST_VISIBLE | vk::MemoryPropertyFlags::HOST_COHERENT,
        ) else {
            d.destroy_buffer(buffer, None);
            return Err("kein passender Speicher".into());
        };
        let memory = match d.allocate_memory(
            &vk::MemoryAllocateInfo::default().allocation_size(req.size).memory_type_index(mem_type),
            None,
        ) {
            Ok(m) => m,
            Err(e) => {
                d.destroy_buffer(buffer, None);
                return Err(format!("vkAllocateMemory: {e}"));
            }
        };

        // Aufräumen passiert am Ende immer – auch bei Fehlern
        let result = (|| -> Result<Vec<u8>, String> {
            d.bind_buffer_memory(buffer, memory, 0).map_err(|e| format!("bind: {e}"))?;

            let cmd = d
                .allocate_command_buffers(
                    &vk::CommandBufferAllocateInfo::default()
                        .command_pool(self.pool)
                        .level(vk::CommandBufferLevel::PRIMARY)
                        .command_buffer_count(1),
                )
                .map_err(|e| format!("cmd alloc: {e}"))?[0];
            let fence = d
                .create_fence(&vk::FenceCreateInfo::default(), None)
                .map_err(|e| format!("fence: {e}"))?;

            let range = vk::ImageSubresourceRange::default()
                .aspect_mask(vk::ImageAspectFlags::COLOR)
                .base_mip_level(0)
                .level_count(1)
                .base_array_layer(layer)
                .layer_count(1);

            // 2) Befehle aufnehmen:
            //    Layout → TRANSFER_SRC, kopieren, Layout zurück
            d.begin_command_buffer(
                cmd,
                &vk::CommandBufferBeginInfo::default().flags(vk::CommandBufferUsageFlags::ONE_TIME_SUBMIT),
            )
            .map_err(|e| format!("begin: {e}"))?;

            let to_src = vk::ImageMemoryBarrier::default()
                .src_access_mask(vk::AccessFlags::COLOR_ATTACHMENT_WRITE)
                .dst_access_mask(vk::AccessFlags::TRANSFER_READ)
                .old_layout(vk::ImageLayout::COLOR_ATTACHMENT_OPTIMAL)
                .new_layout(vk::ImageLayout::TRANSFER_SRC_OPTIMAL)
                .src_queue_family_index(vk::QUEUE_FAMILY_IGNORED)
                .dst_queue_family_index(vk::QUEUE_FAMILY_IGNORED)
                .image(image)
                .subresource_range(range);
            d.cmd_pipeline_barrier(
                cmd,
                vk::PipelineStageFlags::COLOR_ATTACHMENT_OUTPUT,
                vk::PipelineStageFlags::TRANSFER,
                vk::DependencyFlags::empty(),
                &[],
                &[],
                &[to_src],
            );

            let region = vk::BufferImageCopy::default()
                .image_subresource(
                    vk::ImageSubresourceLayers::default()
                        .aspect_mask(vk::ImageAspectFlags::COLOR)
                        .mip_level(0)
                        .base_array_layer(layer)
                        .layer_count(1),
                )
                .image_offset(vk::Offset3D { x, y, z: 0 })
                .image_extent(vk::Extent3D { width: w, height: h, depth: 1 });
            d.cmd_copy_image_to_buffer(cmd, image, vk::ImageLayout::TRANSFER_SRC_OPTIMAL, buffer, &[region]);

            let back = vk::ImageMemoryBarrier::default()
                .src_access_mask(vk::AccessFlags::TRANSFER_READ)
                .dst_access_mask(vk::AccessFlags::COLOR_ATTACHMENT_WRITE)
                .old_layout(vk::ImageLayout::TRANSFER_SRC_OPTIMAL)
                .new_layout(vk::ImageLayout::COLOR_ATTACHMENT_OPTIMAL)
                .src_queue_family_index(vk::QUEUE_FAMILY_IGNORED)
                .dst_queue_family_index(vk::QUEUE_FAMILY_IGNORED)
                .image(image)
                .subresource_range(range);
            d.cmd_pipeline_barrier(
                cmd,
                vk::PipelineStageFlags::TRANSFER,
                vk::PipelineStageFlags::COLOR_ATTACHMENT_OUTPUT,
                vk::DependencyFlags::empty(),
                &[],
                &[],
                &[back],
            );
            d.end_command_buffer(cmd).map_err(|e| format!("end: {e}"))?;

            // 3) Abschicken und warten (max. 1 s)
            let cmds = [cmd];
            let submit = vk::SubmitInfo::default().command_buffers(&cmds);
            let wait = d
                .queue_submit(self.queue, &[submit], fence)
                .and_then(|_| d.wait_for_fences(&[fence], true, 1_000_000_000));
            d.destroy_fence(fence, None);
            d.free_command_buffers(self.pool, &cmds);
            wait.map_err(|e| format!("GPU-Kopie: {e}"))?;

            // 4) Aus dem Puffer lesen
            let ptr = d
                .map_memory(memory, 0, size, vk::MemoryMapFlags::empty())
                .map_err(|e| format!("map: {e}"))?;
            let data = std::slice::from_raw_parts(ptr as *const u8, size as usize).to_vec();
            d.unmap_memory(memory);
            Ok(data)
        })();

        d.destroy_buffer(buffer, None);
        d.free_memory(memory, None);
        result
    }
}

impl VkCtx {
    /// Färbt jede Ebene eines (Rahmen-)Bildes in einer festen Farbe ein.
    /// Danach liegt es im Layout COLOR_ATTACHMENT_OPTIMAL, wie OpenXR es erwartet.
    ///
    /// UNSAFE: `image` muss ein gültiges, gerade geholtes Swapchain-Bild mit
    /// TRANSFER_DST-Flag sein.
    pub unsafe fn fill_layers(&self, image: vk::Image, colors: &[[f32; 4]]) -> Result<(), String> {
        let d = &self.device;
        let cmd = d
            .allocate_command_buffers(
                &vk::CommandBufferAllocateInfo::default()
                    .command_pool(self.pool)
                    .level(vk::CommandBufferLevel::PRIMARY)
                    .command_buffer_count(1),
            )
            .map_err(|e| format!("cmd alloc: {e}"))?[0];
        let fence = d.create_fence(&vk::FenceCreateInfo::default(), None).map_err(|e| format!("fence: {e}"))?;

        let range = |layer: u32| {
            vk::ImageSubresourceRange::default()
                .aspect_mask(vk::ImageAspectFlags::COLOR)
                .level_count(1)
                .base_array_layer(layer)
                .layer_count(1)
        };
        let barrier = |layer: u32, old, new, src, dst| {
            vk::ImageMemoryBarrier::default()
                .src_access_mask(src)
                .dst_access_mask(dst)
                .old_layout(old)
                .new_layout(new)
                .src_queue_family_index(vk::QUEUE_FAMILY_IGNORED)
                .dst_queue_family_index(vk::QUEUE_FAMILY_IGNORED)
                .image(image)
                .subresource_range(range(layer))
        };

        d.begin_command_buffer(cmd, &vk::CommandBufferBeginInfo::default().flags(vk::CommandBufferUsageFlags::ONE_TIME_SUBMIT))
            .map_err(|e| format!("begin: {e}"))?;
        for (i, c) in colors.iter().enumerate() {
            let layer = i as u32;
            d.cmd_pipeline_barrier(
                cmd,
                vk::PipelineStageFlags::TOP_OF_PIPE,
                vk::PipelineStageFlags::TRANSFER,
                vk::DependencyFlags::empty(),
                &[],
                &[],
                &[barrier(layer, vk::ImageLayout::UNDEFINED, vk::ImageLayout::TRANSFER_DST_OPTIMAL,
                    vk::AccessFlags::empty(), vk::AccessFlags::TRANSFER_WRITE)],
            );
            d.cmd_clear_color_image(
                cmd,
                image,
                vk::ImageLayout::TRANSFER_DST_OPTIMAL,
                &vk::ClearColorValue { float32: *c },
                &[range(layer)],
            );
            d.cmd_pipeline_barrier(
                cmd,
                vk::PipelineStageFlags::TRANSFER,
                vk::PipelineStageFlags::COLOR_ATTACHMENT_OUTPUT,
                vk::DependencyFlags::empty(),
                &[],
                &[],
                &[barrier(layer, vk::ImageLayout::TRANSFER_DST_OPTIMAL, vk::ImageLayout::COLOR_ATTACHMENT_OPTIMAL,
                    vk::AccessFlags::TRANSFER_WRITE, vk::AccessFlags::COLOR_ATTACHMENT_READ)],
            );
        }
        d.end_command_buffer(cmd).map_err(|e| format!("end: {e}"))?;

        let cmds = [cmd];
        let res = d
            .queue_submit(self.queue, &[vk::SubmitInfo::default().command_buffers(&cmds)], fence)
            .and_then(|_| d.wait_for_fences(&[fence], true, 1_000_000_000));
        d.destroy_fence(fence, None);
        d.free_command_buffers(self.pool, &cmds);
        res.map_err(|e| format!("GPU-Füllen: {e}"))
    }
}

impl VkCtx {
    /// Lädt Pixel (RGBA/BGRA, w×h×4 pro Ebene) in die Ebenen eines Bildes
    /// (für die Typ-Symbole am Rahmen). Danach Layout COLOR_ATTACHMENT_OPTIMAL.
    ///
    /// UNSAFE: `image` muss ein gültiges, gerade geholtes Swapchain-Bild mit
    /// TRANSFER_DST-Flag und mindestens `layers.len()` Ebenen sein.
    pub unsafe fn upload_layers(&self, image: vk::Image, layers: &[Vec<u8>], w: u32, h: u32) -> Result<(), String> {
        let d = &self.device;
        let layer_size = (w as u64) * (h as u64) * 4;
        let size = layer_size * layers.len() as u64;
        if layers.iter().any(|l| l.len() as u64 != layer_size) {
            return Err("falsche Pixel-Anzahl".into());
        }

        // 1) Zwischenpuffer im RAM-sichtbaren Speicher, Pixel hineinkopieren
        let buffer = d
            .create_buffer(
                &vk::BufferCreateInfo::default()
                    .size(size)
                    .usage(vk::BufferUsageFlags::TRANSFER_SRC)
                    .sharing_mode(vk::SharingMode::EXCLUSIVE),
                None,
            )
            .map_err(|e| format!("vkCreateBuffer: {e}"))?;
        let req = d.get_buffer_memory_requirements(buffer);
        let Some(mem_type) = self.find_memory(
            req.memory_type_bits,
            vk::MemoryPropertyFlags::HOST_VISIBLE | vk::MemoryPropertyFlags::HOST_COHERENT,
        ) else {
            d.destroy_buffer(buffer, None);
            return Err("kein passender Speicher".into());
        };
        let memory = match d.allocate_memory(
            &vk::MemoryAllocateInfo::default().allocation_size(req.size).memory_type_index(mem_type),
            None,
        ) {
            Ok(m) => m,
            Err(e) => {
                d.destroy_buffer(buffer, None);
                return Err(format!("vkAllocateMemory: {e}"));
            }
        };

        let result = (|| -> Result<(), String> {
            d.bind_buffer_memory(buffer, memory, 0).map_err(|e| format!("bind: {e}"))?;
            let ptr = d
                .map_memory(memory, 0, size, vk::MemoryMapFlags::empty())
                .map_err(|e| format!("map: {e}"))? as *mut u8;
            for (i, px) in layers.iter().enumerate() {
                std::ptr::copy_nonoverlapping(px.as_ptr(), ptr.add(i * layer_size as usize), px.len());
            }
            d.unmap_memory(memory);

            // 2) Befehle: Layout → TRANSFER_DST, kopieren, Layout → COLOR_ATTACHMENT
            let cmd = d
                .allocate_command_buffers(
                    &vk::CommandBufferAllocateInfo::default()
                        .command_pool(self.pool)
                        .level(vk::CommandBufferLevel::PRIMARY)
                        .command_buffer_count(1),
                )
                .map_err(|e| format!("cmd alloc: {e}"))?[0];
            let fence = d.create_fence(&vk::FenceCreateInfo::default(), None).map_err(|e| format!("fence: {e}"))?;
            let n = layers.len() as u32;
            let range = vk::ImageSubresourceRange::default()
                .aspect_mask(vk::ImageAspectFlags::COLOR)
                .level_count(1)
                .base_array_layer(0)
                .layer_count(n);
            let barrier = |old, new, src, dst| {
                vk::ImageMemoryBarrier::default()
                    .src_access_mask(src)
                    .dst_access_mask(dst)
                    .old_layout(old)
                    .new_layout(new)
                    .src_queue_family_index(vk::QUEUE_FAMILY_IGNORED)
                    .dst_queue_family_index(vk::QUEUE_FAMILY_IGNORED)
                    .image(image)
                    .subresource_range(range)
            };

            d.begin_command_buffer(cmd, &vk::CommandBufferBeginInfo::default().flags(vk::CommandBufferUsageFlags::ONE_TIME_SUBMIT))
                .map_err(|e| format!("begin: {e}"))?;
            d.cmd_pipeline_barrier(
                cmd,
                vk::PipelineStageFlags::TOP_OF_PIPE,
                vk::PipelineStageFlags::TRANSFER,
                vk::DependencyFlags::empty(),
                &[],
                &[],
                &[barrier(vk::ImageLayout::UNDEFINED, vk::ImageLayout::TRANSFER_DST_OPTIMAL,
                    vk::AccessFlags::empty(), vk::AccessFlags::TRANSFER_WRITE)],
            );
            let regions: Vec<_> = (0..n)
                .map(|i| {
                    vk::BufferImageCopy::default()
                        .buffer_offset(i as u64 * layer_size)
                        .image_subresource(
                            vk::ImageSubresourceLayers::default()
                                .aspect_mask(vk::ImageAspectFlags::COLOR)
                                .mip_level(0)
                                .base_array_layer(i)
                                .layer_count(1),
                        )
                        .image_extent(vk::Extent3D { width: w, height: h, depth: 1 })
                })
                .collect();
            d.cmd_copy_buffer_to_image(cmd, buffer, image, vk::ImageLayout::TRANSFER_DST_OPTIMAL, &regions);
            d.cmd_pipeline_barrier(
                cmd,
                vk::PipelineStageFlags::TRANSFER,
                vk::PipelineStageFlags::COLOR_ATTACHMENT_OUTPUT,
                vk::DependencyFlags::empty(),
                &[],
                &[],
                &[barrier(vk::ImageLayout::TRANSFER_DST_OPTIMAL, vk::ImageLayout::COLOR_ATTACHMENT_OPTIMAL,
                    vk::AccessFlags::TRANSFER_WRITE, vk::AccessFlags::COLOR_ATTACHMENT_READ)],
            );
            d.end_command_buffer(cmd).map_err(|e| format!("end: {e}"))?;

            let cmds = [cmd];
            let res = d
                .queue_submit(self.queue, &[vk::SubmitInfo::default().command_buffers(&cmds)], fence)
                .and_then(|_| d.wait_for_fences(&[fence], true, 1_000_000_000));
            d.destroy_fence(fence, None);
            d.free_command_buffers(self.pool, &cmds);
            res.map_err(|e| format!("GPU-Hochladen: {e}"))
        })();

        d.destroy_buffer(buffer, None);
        d.free_memory(memory, None);
        result
    }
}

impl Drop for VkCtx {
    fn drop(&mut self) {
        // Wird beim Beenden der Session aufgerufen – das VkDevice lebt dann noch.
        unsafe { self.device.destroy_command_pool(self.pool, None) };
    }
}
