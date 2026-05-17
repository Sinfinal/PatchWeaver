# Linux Kernel CVE Repair Summary

This file aggregates the repair guidance for each generated knowledge card.

## CVE-2024-26600
- Title: phy: ti: phy-omap-usb2: Fix NULL pointer dereference for SRP
- Affected files: drivers/phy/ti/phy-omap-usb2.c
- Card: cards/CVE-2024-26600.md

- 补丁主题: phy: ti: phy-omap-usb2: Fix NULL pointer dereference for SRP
- 代码上下文: static int omap_usb_set_vbus(struct usb_otg *otg, bool enabled), static int omap_usb_start_srp(struct usb_otg *otg)
- 建议落地动作:
  - 在 `drivers/phy/ti/phy-omap-usb2.c` 的 `static int omap_usb_set_vbus(struct usb_otg *otg, bool enabled)` 上下文中将 `if (!phy->comparator)` 调整为 `if (!phy->comparator || !phy->comparator->set_vbus)`。
  - 在 `drivers/phy/ti/phy-omap-usb2.c` 的 `static int omap_usb_start_srp(struct usb_otg *otg)` 上下文中将 `if (!phy->comparator)` 调整为 `if (!phy->comparator || !phy->comparator->start_srp)`。

## CVE-2024-26601
- Title: ext4: regenerate buddy after block freeing failed if under fc replay
- Affected files: fs/ext4/mballoc.c
- Card: cards/CVE-2024-26601.md

- 补丁主题: ext4: regenerate buddy after block freeing failed if under fc replay
- 代码上下文: void ext4_mb_generate_buddy(struct super_block *sb,, static void mb_free_blocks(struct inode *inode, struct ext4_buddy *e4b,
- 建议落地动作:
  - 在 `fs/ext4/mballoc.c` 的 `void ext4_mb_generate_buddy(struct super_block *sb,` 上下文中新增 `static void mb_regenerate_buddy(struct ext4_buddy *e4b)`。
  - 在 `fs/ext4/mballoc.c` 的 `static void mb_free_blocks(struct inode *inode, struct ext4_buddy *e4b,` 上下文中新增 `} else {`。

## CVE-2024-26602
- Title: sched/membarrier: reduce the ability to hammer on sys_membarrier
- Affected files: kernel/sched/membarrier.c
- Card: cards/CVE-2024-26602.md

- 补丁主题: sched/membarrier: reduce the ability to hammer on sys_membarrier
- 代码上下文: static int membarrier_global_expedited(void), static int membarrier_private_expedited(int flags), static int sync_runqueues_membarrier_state(struct mm_struct *mm)
- 建议落地动作:
  - 在 `kernel/sched/membarrier.c` 的 `global` 上下文中新增 `static DEFINE_MUTEX(membarrier_ipi_mutex);`。
  - 在 `kernel/sched/membarrier.c` 的 `static int membarrier_global_expedited(void)` 上下文中新增 `mutex_lock(&membarrier_ipi_mutex);`。
  - 在 `kernel/sched/membarrier.c` 的 `static int membarrier_global_expedited(void)` 上下文中新增 `mutex_unlock(&membarrier_ipi_mutex);`。
  - 在 `kernel/sched/membarrier.c` 的 `static int membarrier_private_expedited(int flags)` 上下文中新增 `mutex_lock(&membarrier_ipi_mutex);`。

## CVE-2024-26603
- Title: x86/fpu: Stop relying on userspace for info to fault in xsave buffer
- Affected files: arch/x86/kernel/fpu/signal.c
- Card: cards/CVE-2024-26603.md

- 补丁主题: x86/fpu: Stop relying on userspace for info to fault in xsave buffer
- 代码上下文: static int __restore_fpregs_from_user(void __user *buf, u64 ufeatures,, retry:, static bool __fpu_restore_sig(void __user *buf, void __user *buf_fx,
- 建议落地动作:
  - 在 `arch/x86/kernel/fpu/signal.c` 的 `static int __restore_fpregs_from_user(void __user *buf, u64 ufeatures,` 上下文中将 `static bool restore_fpregs_from_user(void __user *buf, u64 xrestore,` 调整为 `static bool restore_fpregs_from_user(void __user *buf, u64 xrestore, bool fx_only)`。
  - 在 `arch/x86/kernel/fpu/signal.c` 的 `retry:` 上下文中将 `if (!fault_in_readable(buf, size))` 调整为 `if (!fault_in_readable(buf, fpu->fpstate->user_size))`。
  - 在 `arch/x86/kernel/fpu/signal.c` 的 `static bool __fpu_restore_sig(void __user *buf, void __user *buf_fx,` 上下文中移除 `unsigned int state_size;`。
  - 在 `arch/x86/kernel/fpu/signal.c` 的 `static bool __fpu_restore_sig(void __user *buf, void __user *buf_fx,` 上下文中将 `state_size = fx_sw_user.xstate_size;` 调整为 `return restore_fpregs_from_user(buf_fx, user_xfeatures, fx_only);`。

## CVE-2024-26604
- Title: Revert "kobject: Remove redundant checks for whether ktype is NULL"
- Affected files: lib/kobject.c
- Card: cards/CVE-2024-26604.md

- 补丁主题: Revert "kobject: Remove redundant checks for whether ktype is NULL"
- 代码上下文: static int create_dir(struct kobject *kobj), static void __kobject_del(struct kobject *kobj), static void kobject_cleanup(struct kobject *kobj), const struct kobj_ns_type_operations *kobj_child_ns_ops(const struct kobject *pa
- 建议落地动作:
  - 在 `lib/kobject.c` 中调整 `sysfs_create_groups()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `lib/kobject.c` 的 `static int create_dir(struct kobject *kobj)` 上下文中将 `error = sysfs_create_groups(kobj, ktype->default_groups);` 调整为 `if (ktype) {`。
  - 在 `lib/kobject.c` 的 `static void __kobject_del(struct kobject *kobj)` 上下文中将 `sysfs_remove_groups(kobj, ktype->default_groups);` 调整为 `if (ktype)`。
  - 在 `lib/kobject.c` 的 `static void kobject_cleanup(struct kobject *kobj)` 上下文中新增 `if (t && !t->release)`。

## CVE-2024-26605
- Title: PCI/ASPM: Fix deadlock when enabling ASPM
- Affected files: drivers/pci/bus.c, drivers/pci/pci.c, drivers/pci/pci.h, drivers/pci/pcie/aspm.c, include/linux/pci.h
- Card: cards/CVE-2024-26605.md

- 补丁主题: PCI/ASPM: Fix deadlock when enabling ASPM
- 代码上下文: void pci_bus_add_devices(const struct pci_bus *bus), void pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *),, end:, static int pci_set_full_power_state(struct pci_dev *dev), void pci_bus_set_current_state(struct pci_bus *bus, pci_power_t state), static int pci_set_low_power_state(struct pci_dev *dev, pci_power_t state), int pci_set_power_state(struct pci_dev *dev, pci_power_t state), bool pcie_wait_for_link(struct pci_dev *pdev, bool active);
- 建议落地动作:
  - 在该补丁中调整 `down_read()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/pci/bus.c` 的 `void pci_bus_add_devices(const struct pci_bus *bus)` 上下文中将 `/** pci_walk_bus - walk devices on/under bus, calling callback.` 调整为 `static void __pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *),`。
  - 在 `drivers/pci/bus.c` 的 `void pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *),` 上下文中将 `down_read(&pci_bus_sem);` 调整为 `if (!locked)`。
  - 在 `drivers/pci/bus.c` 的 `void pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *),` 上下文中将 `up_read(&pci_bus_sem);` 调整为 `if (!locked)`。

## CVE-2024-26606
- Title: binder: signal epoll threads of self-work
- Affected files: drivers/android/binder.c
- Card: cards/CVE-2024-26606.md

- 补丁主题: binder: signal epoll threads of self-work
- 代码上下文: binder_enqueue_thread_work_ilocked(struct binder_thread *thread,
- 建议落地动作:
  - 在 `drivers/android/binder.c` 的 `binder_enqueue_thread_work_ilocked(struct binder_thread *thread,` 上下文中新增 `/* (e)poll-based threads require an explicit wakeup signal when`。

## CVE-2024-26607
- Title: drm/bridge: sii902x: Fix probing race issue
- Affected files: drivers/gpu/drm/bridge/sii902x.c
- Card: cards/CVE-2024-26607.md

- 补丁主题: drm/bridge: sii902x: Fix probing race issue
- 代码上下文: static int sii902x_init(struct sii902x *sii902x), static int sii902x_probe(struct i2c_client *client)
- 建议落地动作:
  - 在 `drivers/gpu/drm/bridge/sii902x.c` 中将 `drm_bridge_add()` 后移到初始化收尾阶段，在 I2C mux 和外围依赖就绪后再注册 bridge。
  - 在 `drivers/gpu/drm/bridge/sii902x.c` 中调整 `i2c_mux_del_adapters()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/bridge/sii902x.c` 的 `static int sii902x_init(struct sii902x *sii902x)` 上下文中移除 `sii902x->bridge.funcs = &sii902x_bridge_funcs;`。
  - 在 `drivers/gpu/drm/bridge/sii902x.c` 的 `static int sii902x_init(struct sii902x *sii902x)` 上下文中为 `i2c_mux_add_adapter()` 增加返回值检查，失败时立即退出，避免后续流程在未完成初始化时继续执行。

## CVE-2024-26608
- Title: ksmbd: fix global oob in ksmbd_nl_policy
- Affected files: fs/smb/server/ksmbd_netlink.h, fs/smb/server/transport_ipc.c
- Card: cards/CVE-2024-26608.md

- 补丁主题: ksmbd: fix global oob in ksmbd_nl_policy
- 代码上下文: enum ksmbd_event {, static int handle_unsupported_event(struct sk_buff *skb, struct genl_info *info), static int handle_generic_event(struct sk_buff *skb, struct genl_info *info)
- 建议落地动作:
  - 在 `fs/smb/server/ksmbd_netlink.h` 的 `enum ksmbd_event {` 上下文中将 `KSMBD_EVENT_MAX` 调整为 `__KSMBD_EVENT_MAX,`。
  - 在 `fs/smb/server/transport_ipc.c` 的 `static int handle_unsupported_event(struct sk_buff *skb, struct genl_info *info)` 上下文中将 `static const struct nla_policy ksmbd_nl_policy[KSMBD_EVENT_MAX] = {` 调整为 `static const struct nla_policy ksmbd_nl_policy[KSMBD_EVENT_MAX + 1] = {`。
  - 在 `fs/smb/server/transport_ipc.c` 的 `static int handle_generic_event(struct sk_buff *skb, struct genl_info *info)` 上下文中将 `if (type >= KSMBD_EVENT_MAX) {` 调整为 `if (type > KSMBD_EVENT_MAX) {`。

## CVE-2024-26610
- Title: wifi: iwlwifi: fix a memory corruption
- Affected files: drivers/net/wireless/intel/iwlwifi/iwl-dbg-tlv.c
- Card: cards/CVE-2024-26610.md

- 补丁主题: wifi: iwlwifi: fix a memory corruption
- 代码上下文: static int iwl_dbg_tlv_override_trig_node(struct iwl_fw_runtime *fwrt,
- 建议落地动作:
  - 在 `drivers/net/wireless/intel/iwlwifi/iwl-dbg-tlv.c` 的 `static int iwl_dbg_tlv_override_trig_node(struct iwl_fw_runtime *fwrt,` 上下文中将 `memcpy(node_trig->data + offset, trig->data, trig_data_len);` 调整为 `memcpy((u8 *)node_trig->data + offset, trig->data, trig_data_len);`。

## CVE-2024-26611
- Title: xsk: fix usage of multi-buffer BPF helpers for ZC XDP
- Affected files: include/net/xdp_sock_drv.h, net/core/filter.c
- Card: cards/CVE-2024-26611.md

- 补丁主题: xsk: fix usage of multi-buffer BPF helpers for ZC XDP
- 代码上下文: static inline struct xdp_buff *xsk_buff_get_frag(struct xdp_buff *first), static int bpf_xdp_frags_increase_tail(struct xdp_buff *xdp, int offset), static int bpf_xdp_frags_shrink_tail(struct xdp_buff *xdp, int offset)
- 建议落地动作:
  - 在 `include/net/xdp_sock_drv.h` 的 `static inline struct xdp_buff *xsk_buff_get_frag(struct xdp_buff *first)` 上下文中新增 `static inline void xsk_buff_del_tail(struct xdp_buff *tail)`。
  - 在 `net/core/filter.c` 的 `global` 上下文中新增 `#include <net/xdp_sock_drv.h>`。
  - 在 `net/core/filter.c` 的 `static int bpf_xdp_frags_increase_tail(struct xdp_buff *xdp, int offset)` 上下文中新增 `static void bpf_xdp_shrink_data_zc(struct xdp_buff *xdp, int shrink,`。

## CVE-2024-26612
- Title: netfs, fscache: Prevent Oops in fscache_put_cache()
- Affected files: fs/fscache/cache.c
- Card: cards/CVE-2024-26612.md

- 补丁主题: netfs, fscache: Prevent Oops in fscache_put_cache()
- 代码上下文: EXPORT_SYMBOL(fscache_acquire_cache);
- 建议落地动作:
  - 在 `fs/fscache/cache.c` 的 `EXPORT_SYMBOL(fscache_acquire_cache);` 上下文中将 `unsigned int debug_id = cache->debug_id;` 调整为 `unsigned int debug_id;`。

## CVE-2024-26614
- Title: tcp: make sure init the accept_queue's spinlocks once
- Affected files: include/net/inet_connection_sock.h, net/core/request_sock.c, net/ipv4/af_inet.c, net/ipv4/inet_connection_sock.c
- Card: cards/CVE-2024-26614.md

- 补丁主题: tcp: make sure init the accept_queue's spinlocks once
- 代码上下文: static inline bool inet_csk_has_ulp(const struct sock *sk), lookup_protocol:, out:
- 建议落地动作:
  - 在 `include/net/inet_connection_sock.h` 的 `static inline bool inet_csk_has_ulp(const struct sock *sk)` 上下文中新增 `static inline void inet_init_csk_locks(struct sock *sk)`。
  - 在 `net/core/request_sock.c` 的 `global` 上下文中移除 `spin_lock_init(&queue->rskq_lock);`。
  - 在 `net/ipv4/af_inet.c` 的 `lookup_protocol:` 上下文中新增 `if (INET_PROTOSW_ICSK & answer_flags)`。
  - 在 `net/ipv4/inet_connection_sock.c` 的 `out:` 上下文中新增 `if (newsk)`。

## CVE-2024-26615
- Title: net/smc: fix illegal rmb_desc access in SMC-D connection dump
- Affected files: net/smc/smc_diag.c
- Card: cards/CVE-2024-26615.md

- 补丁主题: net/smc: fix illegal rmb_desc access in SMC-D connection dump
- 代码上下文: static int __smc_diag_dump(struct sock *sk, struct sk_buff *skb,
- 建议落地动作:
  - 在 `net/smc/smc_diag.c` 的 `static int __smc_diag_dump(struct sock *sk, struct sk_buff *skb,` 上下文中将 `!list_empty(&smc->conn.lgr->list)) {` 调整为 `!list_empty(&smc->conn.lgr->list) && smc->conn.rmb_desc) {`。

## CVE-2024-26616
- Title: btrfs: scrub: avoid use-after-free when chunk length is not 64K aligned
- Affected files: fs/btrfs/scrub.c
- Card: cards/CVE-2024-26616.md

- 补丁主题: btrfs: scrub: avoid use-after-free when chunk length is not 64K
- 代码上下文: out:, static void scrub_submit_initial_read(struct scrub_ctx *sctx,
- 建议落地动作:
  - 在 `fs/btrfs/scrub.c` 的 `out:` 上下文中将 `bitmap_set(&stripe->io_error_bitmap, 0, stripe->nr_sectors);` 调整为 `struct bio_vec *bvec;`。
  - 在 `fs/btrfs/scrub.c` 的 `static void scrub_submit_initial_read(struct scrub_ctx *sctx,` 上下文中新增 `unsigned int nr_sectors = min(BTRFS_STRIPE_LEN, stripe->bg->start +`。
  - 在 `fs/btrfs/scrub.c` 的 `static void scrub_submit_initial_read(struct scrub_ctx *sctx,` 上下文中将 `/* Read the whole stripe. */` 调整为 `/* Read the whole range inside the chunk boundary. */`。

## CVE-2024-26617
- Title: fs/proc/task_mmu: move mmu notification mechanism inside mm lock
- Affected files: fs/proc/task_mmu.c
- Card: cards/CVE-2024-26617.md

- 补丁主题: fs/proc/task_mmu: move mmu notification mechanism inside mm lock
- 代码上下文: static long pagemap_scan_flush_buffer(struct pagemap_scan_private *p), static long do_pagemap_scan(struct mm_struct *mm, unsigned long uarg)
- 建议落地动作:
  - 在 `fs/proc/task_mmu.c` 中调整 `mmu_notifier_range_init()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `fs/proc/task_mmu.c` 的 `static long pagemap_scan_flush_buffer(struct pagemap_scan_private *p)` 上下文中移除 `struct mmu_notifier_range range;`。
  - 在 `fs/proc/task_mmu.c` 的 `static long do_pagemap_scan(struct mm_struct *mm, unsigned long uarg)` 上下文中将 `/* Protection change for the range is going to happen. */` 调整为 `struct mmu_notifier_range range;`。
  - 在 `fs/proc/task_mmu.c` 的 `static long do_pagemap_scan(struct mm_struct *mm, unsigned long uarg)` 上下文中新增 `/* Protection change for the range is going to happen. */`。

## CVE-2024-26618
- Title: arm64/sme: Always exit sme_alloc() early with existing storage
- Affected files: arch/arm64/kernel/fpsimd.c
- Card: cards/CVE-2024-26618.md

- 补丁主题: arm64/sme: Always exit sme_alloc() early with existing storage
- 代码上下文: void fpsimd_release_task(struct task_struct *dead_task)
- 建议落地动作:
  - 在 `arch/arm64/kernel/fpsimd.c` 的 `void fpsimd_release_task(struct task_struct *dead_task)` 上下文中将 `if (task->thread.sme_state && flush) {` 调整为 `if (task->thread.sme_state) {`。

## CVE-2024-26619
- Title: riscv: Fix module loading free order
- Affected files: arch/riscv/kernel/module.c
- Card: cards/CVE-2024-26619.md

- 补丁主题: riscv: Fix module loading free order
- 代码上下文: static int add_relocation_to_accumulate(struct module *me, int type,
- 建议落地动作:
  - 在 `arch/riscv/kernel/module.c` 的 `static int add_relocation_to_accumulate(struct module *me, int type,` 上下文中调整 `kfree()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `arch/riscv/kernel/module.c` 的 `static int add_relocation_to_accumulate(struct module *me, int type,` 上下文中调整 `kfree()` 的调用位置，使其与新的初始化顺序保持一致。

## CVE-2024-26620
- Title: s390/vfio-ap: always filter entire AP matrix
- Affected files: drivers/s390/crypto/vfio_ap_ops.c
- Card: cards/CVE-2024-26620.md

- 补丁主题: s390/vfio-ap: always filter entire AP matrix
- 代码上下文: static bool vfio_ap_mdev_filter_cdoms(struct ap_matrix_mdev *matrix_mdev), static bool vfio_ap_mdev_filter_matrix(unsigned long *apm, unsigned long *aqm,, static ssize_t assign_adapter_store(struct device *dev,, static ssize_t assign_domain_store(struct device *dev,, int vfio_ap_mdev_probe_queue(struct ap_device *apdev), void vfio_ap_on_cfg_changed(struct ap_config_info *cur_cfg_info,
- 建议落地动作:
  - 在 `drivers/s390/crypto/vfio_ap_ops.c` 的 `static bool vfio_ap_mdev_filter_cdoms(struct ap_matrix_mdev *matrix_mdev)` 上下文中将 `static bool vfio_ap_mdev_filter_matrix(unsigned long *apm, unsigned long *aqm,` 调整为 `static bool vfio_ap_mdev_filter_matrix(struct ap_matrix_mdev *matrix_mdev)`。
  - 在 `drivers/s390/crypto/vfio_ap_ops.c` 的 `static bool vfio_ap_mdev_filter_matrix(unsigned long *apm, unsigned long *aqm,` 上下文中将 `for_each_set_bit_inv(apid, apm, AP_DEVICES) {` 调整为 `for_each_set_bit_inv(apid, matrix_mdev->matrix.apm, AP_DEVICES) {`。
  - 在 `drivers/s390/crypto/vfio_ap_ops.c` 的 `static ssize_t assign_adapter_store(struct device *dev,` 上下文中移除 `DECLARE_BITMAP(apm_delta, AP_DEVICES);`。
  - 在 `drivers/s390/crypto/vfio_ap_ops.c` 的 `static ssize_t assign_adapter_store(struct device *dev,` 上下文中将 `memset(apm_delta, 0, sizeof(apm_delta));` 调整为 `if (vfio_ap_mdev_filter_matrix(matrix_mdev))`。

## CVE-2024-26621
- Title: mm: huge_memory: don't force huge page alignment on 32 bit
- Affected files: mm/huge_memory.c
- Card: cards/CVE-2024-26621.md

- 补丁主题: mm: huge_memory: don't force huge page alignment on 32 bit
- 代码上下文: static unsigned long __thp_get_unmapped_area(struct file *filp,
- 建议落地动作:
  - 在 `mm/huge_memory.c` 的 `global` 上下文中新增 `#include <linux/compat.h>`。
  - 在 `mm/huge_memory.c` 的 `static unsigned long __thp_get_unmapped_area(struct file *filp,` 上下文中新增 `if (IS_ENABLED(CONFIG_32BIT) || in_compat_syscall())`。

## CVE-2024-26622
- Title: tomoyo: fix UAF write bug in tomoyo_write_control()
- Affected files: security/tomoyo/common.c
- Card: cards/CVE-2024-26622.md

- 补丁主题: tomoyo: fix UAF write bug in tomoyo_write_control()
- 代码上下文: ssize_t tomoyo_write_control(struct tomoyo_io_buffer *head,
- 建议落地动作:
  - 在 `security/tomoyo/common.c` 的 `ssize_t tomoyo_write_control(struct tomoyo_io_buffer *head,` 上下文中将 `char *cp0 = head->write_buf;` 调整为 `char *cp0;`。

## CVE-2024-26623
- Title: pds_core: Prevent race issues involving the adminq
- Affected files: drivers/net/ethernet/amd/pds_core/adminq.c, drivers/net/ethernet/amd/pds_core/core.c, drivers/net/ethernet/amd/pds_core/core.h
- Card: cards/CVE-2024-26623.md

- 补丁主题: pds_core: Prevent race issues involving the adminq
- 代码上下文: static int pdsc_process_notifyq(struct pdsc_qcq *qcq), void pdsc_process_adminq(struct pdsc_qcq *qcq), credits:, irqreturn_t pdsc_adminq_isr(int irq, void *data), int pdsc_adminq_post(struct pdsc *pdsc,, err_out:, int pdsc_setup(struct pdsc *pdsc, bool init), void pdsc_stop(struct pdsc *pdsc)
- 建议落地动作:
  - 在 `drivers/net/ethernet/amd/pds_core/adminq.c` 的 `static int pdsc_process_notifyq(struct pdsc_qcq *qcq)` 上下文中新增 `static bool pdsc_adminq_inc_if_up(struct pdsc *pdsc)`。
  - 在 `drivers/net/ethernet/amd/pds_core/adminq.c` 的 `void pdsc_process_adminq(struct pdsc_qcq *qcq)` 上下文中将 `/* Don't process AdminQ when shutting down */` 调整为 `/* Don't process AdminQ when it's not up */`。
  - 在 `drivers/net/ethernet/amd/pds_core/adminq.c` 的 `credits:` 上下文中新增 `refcount_dec(&pdsc->adminq_refcnt);`。
  - 在 `drivers/net/ethernet/amd/pds_core/adminq.c` 的 `irqreturn_t pdsc_adminq_isr(int irq, void *data)` 上下文中将 `/* Don't process AdminQ when shutting down */` 调整为 `/* Don't process AdminQ when it's not up */`。

## CVE-2024-26625
- Title: llc: call sock_orphan() at release time
- Affected files: net/llc/af_llc.c
- Card: cards/CVE-2024-26625.md

- 补丁主题: llc: call sock_orphan() at release time
- 代码上下文: static int llc_ui_release(struct socket *sock)
- 建议落地动作:
  - 在 `net/llc/af_llc.c` 的 `static int llc_ui_release(struct socket *sock)` 上下文中新增 `sock_orphan(sk);`。

## CVE-2024-26626
- Title: ipmr: fix kernel panic when forwarding mcast packets
- Affected files: include/net/ip.h, net/ipv4/ip_sockglue.c, net/ipv4/ipmr.c, net/ipv4/raw.c, net/ipv4/udp.c
- Card: cards/CVE-2024-26626.md

- 补丁主题: ipmr: fix kernel panic when forwarding mcast packets
- 代码上下文: int ip_options_rcv_srr(struct sk_buff *skb, struct net_device *dev);, e_inval:, void ipv4_pktinfo_prepare(const struct sock *sk, struct sk_buff *skb), static int ipmr_cache_report(const struct mr_table *mrt,, static int raw_rcv_skb(struct sock *sk, struct sk_buff *skb), static int udp_queue_rcv_one_skb(struct sock *sk, struct sk_buff *skb)
- 建议落地动作:
  - 在该补丁中调整 `skb_dst_drop()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `include/net/ip.h` 的 `int ip_options_rcv_srr(struct sk_buff *skb, struct net_device *dev);` 上下文中将 `void ipv4_pktinfo_prepare(const struct sock *sk, struct sk_buff *skb);` 调整为 `void ipv4_pktinfo_prepare(const struct sock *sk, struct sk_buff *skb, bool drop_dst);`。
  - 在 `net/ipv4/ip_sockglue.c` 的 `e_inval:` 上下文中将 `void ipv4_pktinfo_prepare(const struct sock *sk, struct sk_buff *skb)` 调整为 `* @drop_dst: if true, drops skb dst`。
  - 在 `net/ipv4/ip_sockglue.c` 的 `void ipv4_pktinfo_prepare(const struct sock *sk, struct sk_buff *skb)` 上下文中将 `skb_dst_drop(skb);` 调整为 `if (drop_dst)`。

## CVE-2024-26627
- Title: scsi: core: Move scsi_host_busy() out of host lock for waking up EH handler
- Affected files: drivers/scsi/scsi_error.c, drivers/scsi/scsi_lib.c, drivers/scsi/scsi_priv.h
- Card: cards/CVE-2024-26627.md

- 补丁主题: scsi: core: Move scsi_host_busy() out of host lock for waking up EH
- 代码上下文: static int scsi_eh_try_stu(struct scsi_cmnd *scmd);, void scsi_schedule_eh(struct Scsi_Host *shost), static void scsi_eh_inc_host_failed(struct rcu_head *head), static void scsi_dec_host_busy(struct Scsi_Host *shost, struct scsi_cmnd *cmd), extern void scmd_eh_abort_handler(struct work_struct *work);
- 建议落地动作:
  - 在 `drivers/scsi/scsi_error.c` 的 `static int scsi_eh_try_stu(struct scsi_cmnd *scmd);` 上下文中将 `void scsi_eh_wakeup(struct Scsi_Host *shost)` 调整为 `void scsi_eh_wakeup(struct Scsi_Host *shost, unsigned int busy)`。
  - 在 `drivers/scsi/scsi_error.c` 的 `void scsi_schedule_eh(struct Scsi_Host *shost)` 上下文中将 `scsi_eh_wakeup(shost);` 调整为 `scsi_eh_wakeup(shost, scsi_host_busy(shost));`。
  - 在 `drivers/scsi/scsi_error.c` 的 `static void scsi_eh_inc_host_failed(struct rcu_head *head)` 上下文中将 `scsi_eh_wakeup(shost);` 调整为 `scsi_eh_wakeup(shost, scsi_host_busy(shost));`。
  - 在 `drivers/scsi/scsi_lib.c` 的 `static void scsi_dec_host_busy(struct Scsi_Host *shost, struct scsi_cmnd *cmd)` 上下文中将 `scsi_eh_wakeup(shost);` 调整为 `scsi_eh_wakeup(shost, scsi_host_busy(shost));`。

## CVE-2024-26629
- Title: nfsd: fix RELEASE_LOCKOWNER
- Affected files: fs/nfsd/nfs4state.c
- Card: cards/CVE-2024-26629.md

- 补丁主题: Revert "NFSD: Fix possible sleep during nfsd4_release_lockowner()"
- 代码上下文: nfsd4_release_lockowner(struct svc_rqst *rqstp,
- 建议落地动作:
  - 在 `fs/nfsd/nfs4state.c` 的 `nfsd4_release_lockowner(struct svc_rqst *rqstp,` 上下文中调整 `spin_unlock()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `fs/nfsd/nfs4state.c` 的 `nfsd4_release_lockowner(struct svc_rqst *rqstp,` 上下文中将 `if (atomic_read(&sop->so_count) != 1) {` 调整为 `/* see if there are still any locks associated with it */`。

## CVE-2024-26630
- Title: mm: cachestat: fix folio read-after-free in cache walk
- Affected files: mm/filemap.c
- Card: cards/CVE-2024-26630.md

- 补丁主题: mm: cachestat: fix folio read-after-free in cache walk
- 代码上下文: static void filemap_cachestat(struct address_space *mapping,
- 建议落地动作:
  - 在 `mm/filemap.c` 的 `static void filemap_cachestat(struct address_space *mapping,` 上下文中调整 `round_down()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `mm/filemap.c` 的 `static void filemap_cachestat(struct address_space *mapping,` 上下文中将 `int order = xa_get_order(xas.xa, xas.xa_index);` 调整为 `int order;`。
  - 在 `mm/filemap.c` 的 `static void filemap_cachestat(struct address_space *mapping,` 上下文中将 `nr_pages = folio_nr_pages(folio);` 调整为 `if (xas_get_mark(&xas, PAGECACHE_TAG_DIRTY))`。

## CVE-2024-26631
- Title: ipv6: mcast: fix data-race in ipv6_mc_down / mld_ifc_work
- Affected files: net/ipv6/mcast.c
- Card: cards/CVE-2024-26631.md

- 补丁主题: ipv6: mcast: fix data-race in ipv6_mc_down / mld_ifc_work
- 代码上下文: void ipv6_mc_down(struct inet6_dev *idev)
- 建议落地动作:
  - 在 `net/ipv6/mcast.c` 的 `void ipv6_mc_down(struct inet6_dev *idev)` 上下文中新增 `mutex_lock(&idev->mc_lock);`。

## CVE-2024-26632
- Title: block: Fix iterating over an empty bio with bio_for_each_folio_all
- Affected files: include/linux/bio.h
- Card: cards/CVE-2024-26632.md

- 补丁主题: block: Fix iterating over an empty bio with bio_for_each_folio_all
- 代码上下文: static inline void bio_first_folio(struct folio_iter *fi, struct bio *bio,, static inline void bio_next_folio(struct folio_iter *fi, struct bio *bio)
- 建议落地动作:
  - 在 `include/linux/bio.h` 中调整 `bio_first_folio()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `include/linux/bio.h` 的 `static inline void bio_first_folio(struct folio_iter *fi, struct bio *bio,` 上下文中新增 `if (unlikely(i >= bio->bi_vcnt)) {`。
  - 在 `include/linux/bio.h` 的 `static inline void bio_next_folio(struct folio_iter *fi, struct bio *bio)` 上下文中将 `} else if (fi->_i + 1 < bio->bi_vcnt) {` 调整为 `bio_first_folio(fi, bio, fi->_i + 1);`。

## CVE-2024-26633
- Title: ip6_tunnel: fix NEXTHDR_FRAGMENT handling in ip6_tnl_parse_tlv_enc_lim()
- Affected files: net/ipv6/ip6_tunnel.c
- Card: cards/CVE-2024-26633.md

- 补丁主题: ip6_tunnel: fix NEXTHDR_FRAGMENT handling in
- 代码上下文: __u16 ip6_tnl_parse_tlv_enc_lim(struct sk_buff *skb, __u8 *raw)
- 建议落地动作:
  - 在 `net/ipv6/ip6_tunnel.c` 的 `__u16 ip6_tnl_parse_tlv_enc_lim(struct sk_buff *skb, __u8 *raw)` 上下文中调整 `pskb_may_pull()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/ipv6/ip6_tunnel.c` 的 `__u16 ip6_tnl_parse_tlv_enc_lim(struct sk_buff *skb, __u8 *raw)` 上下文中将 `u8 next, nexthdr = ipv6h->nexthdr;` 调整为 `u8 nexthdr = ipv6h->nexthdr;`。
  - 在 `net/ipv6/ip6_tunnel.c` 的 `__u16 ip6_tnl_parse_tlv_enc_lim(struct sk_buff *skb, __u8 *raw)` 上下文中将 `struct frag_hdr *frag_hdr = (struct frag_hdr *) hdr;` 调整为 `if (!pskb_may_pull(skb, off + optlen))`。
  - 在 `net/ipv6/ip6_tunnel.c` 的 `__u16 ip6_tnl_parse_tlv_enc_lim(struct sk_buff *skb, __u8 *raw)` 上下文中将 `nexthdr = next;` 调整为 `nexthdr = hdr->nexthdr;`。

## CVE-2024-26634
- Title: net: fix removing a namespace with conflicting altnames
- Affected files: net/core/dev.c, net/core/dev.h
- Card: cards/CVE-2024-26634.md

- 补丁主题: net: fix removing a namespace with conflicting altnames
- 代码上下文: static struct pernet_operations __net_initdata netdev_net_ops = {, static void __net_exit default_device_exit_net(struct net *net), int dev_change_name(struct net_device *dev, const char *newname);
- 建议落地动作:
  - 在 `net/core/dev.c` 的 `static struct pernet_operations __net_initdata netdev_net_ops = {` 上下文中新增 `struct netdev_name_node *name_node, *tmp;`。
  - 在 `net/core/dev.c` 的 `static void __net_exit default_device_exit_net(struct net *net)` 上下文中新增 `netdev_for_each_altname_safe(dev, name_node, tmp)`。
  - 在 `net/core/dev.h` 的 `int dev_change_name(struct net_device *dev, const char *newname);` 上下文中新增 `#define netdev_for_each_altname_safe(dev, namenode, next) \`。

## CVE-2024-26635
- Title: llc: Drop support for ETH_P_TR_802_2.
- Affected files: include/net/llc_pdu.h, net/llc/llc_core.c
- Card: cards/CVE-2024-26635.md

- 补丁主题: llc: Drop support for ETH_P_TR_802_2.
- 代码上下文: static inline void llc_pdu_header_init(struct sk_buff *skb, u8 type,, static inline void llc_pdu_decode_sa(struct sk_buff *skb, u8 *sa), static struct packet_type llc_packet_type __read_mostly = {
- 建议落地动作:
  - 在该补丁中调整 `memcpy()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `include/net/llc_pdu.h` 的 `static inline void llc_pdu_header_init(struct sk_buff *skb, u8 type,` 上下文中将 `if (skb->protocol == htons(ETH_P_802_2))` 调整为 `memcpy(sa, eth_hdr(skb)->h_source, ETH_ALEN);`。
  - 在 `include/net/llc_pdu.h` 的 `static inline void llc_pdu_decode_sa(struct sk_buff *skb, u8 *sa)` 上下文中将 `if (skb->protocol == htons(ETH_P_802_2))` 调整为 `memcpy(da, eth_hdr(skb)->h_dest, ETH_ALEN);`。
  - 在 `net/llc/llc_core.c` 的 `static struct packet_type llc_packet_type __read_mostly = {` 上下文中移除 `static struct packet_type llc_tr_packet_type __read_mostly = {`。

## CVE-2024-26636
- Title: llc: make llc_ui_sendmsg() more robust against bonding changes
- Affected files: net/llc/af_llc.c
- Card: cards/CVE-2024-26636.md

- 补丁主题: llc: make llc_ui_sendmsg() more robust against bonding changes
- 代码上下文: copy_uaddr:, static int llc_ui_sendmsg(struct socket *sock, struct msghdr *msg, size_t len)
- 建议落地动作:
  - 在 `net/llc/af_llc.c` 中调整 `DECLARE_SOCKADDR()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/llc/af_llc.c` 的 `copy_uaddr:` 上下文中调整 `DECLARE_SOCKADDR()` 的调用位置，使其与新的初始化顺序保持一致。
  - 在 `net/llc/af_llc.c` 的 `static int llc_ui_sendmsg(struct socket *sock, struct msghdr *msg, size_t len)` 上下文中将 `hdrlen = llc->dev->hard_header_len + llc_ui_header_len(sk, addr);` 调整为 `dev = llc->dev;`。

## CVE-2024-26637
- Title: wifi: ath11k: rely on mac80211 debugfs handling for vif
- Affected files: drivers/net/wireless/ath/ath11k/core.h, drivers/net/wireless/ath/ath11k/debugfs.c, drivers/net/wireless/ath/ath11k/debugfs.h, drivers/net/wireless/ath/ath11k/mac.c
- Card: cards/CVE-2024-26637.md

- 补丁主题: wifi: ath11k: rely on mac80211 debugfs handling for vif
- 代码上下文: struct ath11k_vif {, static const struct file_operations ath11k_fops_twt_resume_dialog = {, static inline int ath11k_debugfs_rx_filter(struct ath11k *ar), static inline int ath11k_debugfs_get_fw_stats(struct ath11k *ar,, static int ath11k_mac_op_add_interface(struct ieee80211_hw *hw,, err_vdev_del:, static const struct ieee80211_ops ath11k_ops = {
- 建议落地动作:
  - 在 `drivers/net/wireless/ath/ath11k/core.h` 的 `struct ath11k_vif {` 上下文中移除 `#ifdef CONFIG_ATH11K_DEBUGFS`。
  - 在 `drivers/net/wireless/ath/ath11k/debugfs.c` 的 `static const struct file_operations ath11k_fops_twt_resume_dialog = {` 上下文中将 `void ath11k_debugfs_add_interface(struct ath11k_vif *arvif)` 调整为 `void ath11k_debugfs_op_vif_add(struct ieee80211_hw *hw,`。
  - 在 `drivers/net/wireless/ath/ath11k/debugfs.h` 的 `static inline int ath11k_debugfs_rx_filter(struct ath11k *ar)` 上下文中将 `void ath11k_debugfs_add_interface(struct ath11k_vif *arvif);` 调整为 `void ath11k_debugfs_op_vif_add(struct ieee80211_hw *hw,`。
  - 在 `drivers/net/wireless/ath/ath11k/debugfs.h` 的 `static inline int ath11k_debugfs_get_fw_stats(struct ath11k *ar,` 上下文中移除 `static inline void ath11k_debugfs_add_interface(struct ath11k_vif *arvif)`。

## CVE-2024-26638
- Title: nbd: always initialize struct msghdr completely
- Affected files: drivers/block/nbd.c
- Card: cards/CVE-2024-26638.md

- 补丁主题: nbd: always initialize struct msghdr completely
- 代码上下文: static int __sock_xmit(struct nbd_device *nbd, struct socket *sock, int send,
- 建议落地动作:
  - 在 `drivers/block/nbd.c` 的 `static int __sock_xmit(struct nbd_device *nbd, struct socket *sock, int send,` 上下文中将 `struct msghdr msg;` 调整为 `struct msghdr msg = {} ;`。
  - 在 `drivers/block/nbd.c` 的 `static int __sock_xmit(struct nbd_device *nbd, struct socket *sock, int send,` 上下文中移除 `msg.msg_name = NULL;`。

## CVE-2024-26640
- Title: tcp: add sanity checks to rx zerocopy
- Affected files: net/ipv4/tcp.c
- Card: cards/CVE-2024-26640.md

- 补丁主题: tcp: add sanity checks to rx zerocopy
- 代码上下文: static skb_frag_t *skb_advance_to_frag(struct sk_buff *skb, u32 offset_skb,
- 建议落地动作:
  - 在 `net/ipv4/tcp.c` 的 `static skb_frag_t *skb_advance_to_frag(struct sk_buff *skb, u32 offset_skb,` 上下文中将 `return skb_frag_size(frag) == PAGE_SIZE && !skb_frag_off(frag);` 调整为 `struct page *page;`。

## CVE-2024-26641
- Title: ip6_tunnel: make sure to pull inner header in __ip6_tnl_rcv()
- Affected files: net/ipv6/ip6_tunnel.c
- Card: cards/CVE-2024-26641.md

- 补丁主题: ip6_tunnel: make sure to pull inner header in __ip6_tnl_rcv()
- 代码上下文: static int __ip6_tnl_rcv(struct ip6_tnl *tunnel, struct sk_buff *skb,
- 建议落地动作:
  - 在 `net/ipv6/ip6_tunnel.c` 的 `static int __ip6_tnl_rcv(struct ip6_tnl *tunnel, struct sk_buff *skb,` 上下文中将 `const struct ipv6hdr *ipv6h = ipv6_hdr(skb);` 调整为 `const struct ipv6hdr *ipv6h;`。
  - 在 `net/ipv6/ip6_tunnel.c` 的 `static int __ip6_tnl_rcv(struct ip6_tnl *tunnel, struct sk_buff *skb,` 上下文中移除 `ipv6h = ipv6_hdr(skb);`。
  - 在 `net/ipv6/ip6_tunnel.c` 的 `static int __ip6_tnl_rcv(struct ip6_tnl *tunnel, struct sk_buff *skb,` 上下文中新增 `/* Save offset of outer header relative to skb->head,`。

## CVE-2024-26642
- Title: netfilter: nf_tables: disallow anonymous set with timeout flag
- Affected files: net/netfilter/nf_tables_api.c
- Card: cards/CVE-2024-26642.md

- 补丁主题: netfilter: nf_tables: disallow anonymous set with timeout flag
- 代码上下文: static int nf_tables_newset(struct sk_buff *skb, const struct nfnl_info *info,
- 建议落地动作:
  - 在 `net/netfilter/nf_tables_api.c` 的 `static int nf_tables_newset(struct sk_buff *skb, const struct nfnl_info *info,` 上下文中新增 `if ((flags & (NFT_SET_ANONYMOUS | NFT_SET_TIMEOUT | NFT_SET_EVAL)) ==`。

## CVE-2024-26643
- Title: netfilter: nf_tables: mark set as dead when unbinding anonymous set with timeout
- Affected files: net/netfilter/nf_tables_api.c
- Card: cards/CVE-2024-26643.md

- 补丁主题: netfilter: nf_tables: mark set as dead when unbinding anonymous set
- 代码上下文: static void nf_tables_unbind_set(const struct nft_ctx *ctx, struct nft_set *set,
- 建议落地动作:
  - 在 `net/netfilter/nf_tables_api.c` 的 `static void nf_tables_unbind_set(const struct nft_ctx *ctx, struct nft_set *set,` 上下文中新增 `set->dead = 1;`。

## CVE-2024-26644
- Title: btrfs: don't abort filesystem when attempting to snapshot deleted subvolume
- Affected files: fs/btrfs/ioctl.c
- Card: cards/CVE-2024-26644.md

- 补丁主题: btrfs: don't abort filesystem when attempting to snapshot deleted
- 代码上下文: static int create_snapshot(struct btrfs_root *root, struct inode *dir,
- 建议落地动作:
  - 在 `fs/btrfs/ioctl.c` 的 `static int create_snapshot(struct btrfs_root *root, struct inode *dir,` 上下文中新增 `if (btrfs_root_refs(&root->root_item) == 0)`。

## CVE-2024-26645
- Title: tracing: Ensure visibility when inserting an element into tracing_map
- Affected files: kernel/trace/tracing_map.c
- Card: cards/CVE-2024-26645.md

- 补丁主题: tracing: Ensure visibility when inserting an element into tracing_map
- 代码上下文: __tracing_map_insert(struct tracing_map *map, void *key, bool lookup_only)
- 建议落地动作:
  - 在 `kernel/trace/tracing_map.c` 的 `__tracing_map_insert(struct tracing_map *map, void *key, bool lookup_only)` 上下文中将 `entry->val = elt;` 调整为 `* Ensure the initialization is visible and`。

## CVE-2024-26646
- Title: thermal: intel: hfi: Add syscore callbacks for system-wide PM
- Affected files: drivers/thermal/intel/intel_hfi.c
- Card: cards/CVE-2024-26646.md

- 补丁主题: thermal: intel: hfi: Add syscore callbacks for system-wide PM
- 代码上下文: static __init int hfi_parse_features(void), void __init intel_hfi_init(void)
- 建议落地动作:
  - 在 `drivers/thermal/intel/intel_hfi.c` 的 `global` 上下文中新增 `#include <linux/suspend.h>`。
  - 在 `drivers/thermal/intel/intel_hfi.c` 的 `static __init int hfi_parse_features(void)` 上下文中新增 `static void hfi_do_enable(void)`。
  - 在 `drivers/thermal/intel/intel_hfi.c` 的 `void __init intel_hfi_init(void)` 上下文中新增 `register_syscore_ops(&hfi_pm_ops);`。

## CVE-2024-26647
- Title: drm/amd/display: Fix late derefrence 'dsc' check in 'link_set_dsc_pps_packet()'
- Affected files: drivers/gpu/drm/amd/display/dc/link/link_dpms.c
- Card: cards/CVE-2024-26647.md

- 补丁主题: drm/amd/display: Fix late derefrence 'dsc' check in
- 代码上下文: bool link_set_dsc_pps_packet(struct pipe_ctx *pipe_ctx, bool enable, bool immedi
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/link/link_dpms.c` 的 `bool link_set_dsc_pps_packet(struct pipe_ctx *pipe_ctx, bool enable, bool immedi` 上下文中调整 `DC_LOGGER_INIT()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/amd/display/dc/link/link_dpms.c` 的 `bool link_set_dsc_pps_packet(struct pipe_ctx *pipe_ctx, bool enable, bool immedi` 上下文中将 `DC_LOGGER_INIT(dsc->ctx->logger);` 调整为 `if (!pipe_ctx->stream->timing.flags.DSC)`。

## CVE-2024-26648
- Title: drm/amd/display: Fix variable deferencing before NULL check in edp_setup_replay()
- Affected files: drivers/gpu/drm/amd/display/dc/link/protocols/link_edp_panel_control.c
- Card: cards/CVE-2024-26648.md

- 补丁主题: drm/amd/display: Fix variable deferencing before NULL check in
- 代码上下文: bool edp_get_replay_state(const struct dc_link *link, uint64_t *state), bool edp_setup_replay(struct dc_link *link, const struct dc_stream_state *stream
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/link/protocols/link_edp_panel_control.c` 的 `bool edp_get_replay_state(const struct dc_link *link, uint64_t *state)` 上下文中将 `struct dc *dc = link->ctx->dc;` 调整为 `struct dc *dc;`。
  - 在 `drivers/gpu/drm/amd/display/dc/link/protocols/link_edp_panel_control.c` 的 `bool edp_setup_replay(struct dc_link *link, const struct dc_stream_state *stream` 上下文中新增 `dc = link->ctx->dc;`。
  - 在 `drivers/gpu/drm/amd/display/dc/link/protocols/link_edp_panel_control.c` 的 `bool edp_setup_replay(struct dc_link *link, const struct dc_stream_state *stream` 上下文中将 `if (replay)` 调整为 `link->replay_settings.replay_feature_enabled =`。

## CVE-2024-26649
- Title: drm/amdgpu: Fix the null pointer when load rlc firmware
- Affected files: drivers/gpu/drm/amd/amdgpu/gfx_v10_0.c
- Card: cards/CVE-2024-26649.md

- 补丁主题: drm/amdgpu: Fix the null pointer when load rlc firmware
- 代码上下文: static int gfx_v10_0_init_microcode(struct amdgpu_device *adev)
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/amdgpu/gfx_v10_0.c` 的 `static int gfx_v10_0_init_microcode(struct amdgpu_device *adev)` 上下文中将 `err = amdgpu_ucode_request(adev, &adev->gfx.rlc_fw, fw_name);` 调整为 `err = request_firmware(&adev->gfx.rlc_fw, fw_name, adev->dev);`。

## CVE-2024-26651
- Title: sr9800: Add check for usbnet_get_endpoints
- Affected files: drivers/net/usb/sr9800.c
- Card: cards/CVE-2024-26651.md

- 补丁主题: sr9800: Add check for usbnet_get_endpoints
- 代码上下文: static int sr9800_bind(struct usbnet *dev, struct usb_interface *intf)
- 建议落地动作:
  - 在 `drivers/net/usb/sr9800.c` 的 `static int sr9800_bind(struct usbnet *dev, struct usb_interface *intf)` 上下文中为 `usbnet_get_endpoints()` 增加返回值检查，失败时立即退出，避免后续流程在未完成初始化时继续执行。

## CVE-2024-26652
- Title: net: pds_core: Fix possible double free in error handling path
- Affected files: drivers/net/ethernet/amd/pds_core/auxbus.c
- Card: cards/CVE-2024-26652.md

- 补丁主题: net: pds_core: Fix possible double free in error handling path
- 代码上下文: static struct pds_auxiliary_dev *pdsc_auxbus_dev_register(struct pdsc *cf,
- 建议落地动作:
  - 在 `drivers/net/ethernet/amd/pds_core/auxbus.c` 的 `static struct pds_auxiliary_dev *pdsc_auxbus_dev_register(struct pdsc *cf,` 上下文中调整 `auxiliary_device_uninit()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/net/ethernet/amd/pds_core/auxbus.c` 的 `static struct pds_auxiliary_dev *pdsc_auxbus_dev_register(struct pdsc *cf,` 上下文中将 `goto err_out;` 调整为 `kfree(padev);`。

## CVE-2024-26653
- Title: usb: misc: ljca: Fix double free in error handling path
- Affected files: drivers/usb/misc/usb-ljca.c
- Card: cards/CVE-2024-26653.md

- 补丁主题: usb: misc: ljca: Fix double free in error handling path
- 代码上下文: static int ljca_new_client_device(struct ljca_adapter *adap, u8 type, u8 id,, static int ljca_enumerate_gpio(struct ljca_adapter *adap), static int ljca_enumerate_i2c(struct ljca_adapter *adap), static int ljca_enumerate_spi(struct ljca_adapter *adap)
- 建议落地动作:
  - 在 `drivers/usb/misc/usb-ljca.c` 的 `static int ljca_new_client_device(struct ljca_adapter *adap, u8 type, u8 id,` 上下文中将 `if (!client)` 调整为 `if (!client) {`。
  - 在 `drivers/usb/misc/usb-ljca.c` 的 `static int ljca_new_client_device(struct ljca_adapter *adap, u8 type, u8 id,` 上下文中将 `if (ret)` 调整为 `if (ret) {`。
  - 在 `drivers/usb/misc/usb-ljca.c` 的 `static int ljca_enumerate_gpio(struct ljca_adapter *adap)` 上下文中将 `ret = ljca_new_client_device(adap, LJCA_CLIENT_GPIO, 0, "ljca-gpio",` 调整为 `return ljca_new_client_device(adap, LJCA_CLIENT_GPIO, 0, "ljca-gpio",`。
  - 在 `drivers/usb/misc/usb-ljca.c` 的 `static int ljca_enumerate_i2c(struct ljca_adapter *adap)` 上下文中将 `if (ret) {` 调整为 `if (ret)`。

## CVE-2024-26654
- Title: ALSA: sh: aica: reorder cleanup operations to avoid UAF bugs
- Affected files: sound/sh/aica.c
- Card: cards/CVE-2024-26654.md

- 补丁主题: ALSA: sh: aica: reorder cleanup operations to avoid UAF bugs
- 代码上下文: static void run_spu_dma(struct work_struct *work), static void aica_period_elapsed(struct timer_list *t), static int snd_aicapcm_pcm_open(struct snd_pcm_substream, static const struct snd_pcm_ops snd_aicapcm_playback_ops = {
- 建议落地动作:
  - 在 `sound/sh/aica.c` 中调整 `mod_timer()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `sound/sh/aica.c` 的 `static void run_spu_dma(struct work_struct *work)` 上下文中将 `mod_timer(&dreamcastcard->timer, jiffies + 1);` 调整为 `if (snd_pcm_running(dreamcastcard->substream))`。
  - 在 `sound/sh/aica.c` 的 `static void aica_period_elapsed(struct timer_list *t)` 上下文中新增 `if (!snd_pcm_running(substream))`。
  - 在 `sound/sh/aica.c` 的 `static int snd_aicapcm_pcm_open(struct snd_pcm_substream` 上下文中将 `flush_work(&(dreamcastcard->spu_dma_work));` 调整为 `static int snd_aicapcm_pcm_sync_stop(struct snd_pcm_substream *substream)`。

## CVE-2024-26655
- Title: Fix memory leak in posix_clock_open()
- Affected files: kernel/time/posix-clock.c
- Card: cards/CVE-2024-26655.md

- 补丁主题: Fix memory leak in posix_clock_open()
- 代码上下文: static int posix_clock_open(struct inode *inode, struct file *fp)
- 建议落地动作:
  - 在 `kernel/time/posix-clock.c` 的 `static int posix_clock_open(struct inode *inode, struct file *fp)` 上下文中调整 `get_device()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `kernel/time/posix-clock.c` 的 `static int posix_clock_open(struct inode *inode, struct file *fp)` 上下文中将 `fp->private_data = pccontext;` 调整为 `if (clk->ops.open) {`。

## CVE-2024-26656
- Title: drm/amdgpu: fix use-after-free bug
- Affected files: drivers/gpu/drm/amd/amdgpu/amdgpu_hmm.c
- Card: cards/CVE-2024-26656.md

- 补丁主题: drm/amdgpu: fix use-after-free bug
- 代码上下文: static const struct mmu_interval_notifier_ops amdgpu_hmm_hsa_ops = {
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/amdgpu/amdgpu_hmm.c` 的 `static const struct mmu_interval_notifier_ops amdgpu_hmm_hsa_ops = {` 上下文中调整 `amdgpu_bo_size()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/amd/amdgpu/amdgpu_hmm.c` 的 `static const struct mmu_interval_notifier_ops amdgpu_hmm_hsa_ops = {` 上下文中将 `return mmu_interval_notifier_insert(&bo->notifier, current->mm,` 调整为 `int r;`。

## CVE-2024-26657
- Title: drm/sched: fix null-ptr-deref in init entity
- Affected files: drivers/gpu/drm/scheduler/sched_entity.c
- Card: cards/CVE-2024-26657.md

- 补丁主题: drm/sched: fix null-ptr-deref in init entity
- 代码上下文: int drm_sched_entity_init(struct drm_sched_entity *entity,
- 建议落地动作:
  - 在 `drivers/gpu/drm/scheduler/sched_entity.c` 的 `int drm_sched_entity_init(struct drm_sched_entity *entity,` 上下文中将 `if (!sched_list[0]->sched_rq) {` 调整为 `* It's perfectly valid to initialize an entity without having a valid`。

## CVE-2024-26658
- Title: bcachefs: grab s_umount only if snapshotting
- Affected files: fs/bcachefs/fs-ioctl.c
- Card: cards/CVE-2024-26658.md

- 补丁主题: bcachefs: grab s_umount only if snapshotting
- 代码上下文: static long __bch2_ioctl_subvolume_create(struct bch_fs *c, struct file *filp,, err2:
- 建议落地动作:
  - 在 `fs/bcachefs/fs-ioctl.c` 中调整 `down_read()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `fs/bcachefs/fs-ioctl.c` 的 `static long __bch2_ioctl_subvolume_create(struct bch_fs *c, struct file *filp,` 上下文中将 `/* why do we need this lock? */` 调整为 `if (arg.flags & BCH_SUBVOL_SNAPSHOT_CREATE) {`。
  - 在 `fs/bcachefs/fs-ioctl.c` 的 `err2:` 上下文中移除 `up_read(&c->vfs_sb->s_umount);`。

## CVE-2024-26659
- Title: xhci: handle isoc Babble and Buffer Overrun events properly
- Affected files: drivers/usb/host/xhci-ring.c
- Card: cards/CVE-2024-26659.md

- 补丁主题: xhci: handle isoc Babble and Buffer Overrun events properly
- 代码上下文: static int process_isoc_td(struct xhci_hcd *xhci, struct xhci_virt_ep *ep,
- 建议落地动作:
  - 在 `drivers/usb/host/xhci-ring.c` 的 `static int process_isoc_td(struct xhci_hcd *xhci, struct xhci_virt_ep *ep,` 上下文中将 `case COMP_ISOCH_BUFFER_OVERRUN:` 调整为 `sum_trbs_for_length = true;`。

## CVE-2024-26660
- Title: drm/amd/display: Implement bounds check for stream encoder creation in DCN301
- Affected files: drivers/gpu/drm/amd/display/dc/dcn301/dcn301_resource.c
- Card: cards/CVE-2024-26660.md

- 补丁主题: drm/amd/display: Implement bounds check for stream encoder creation
- 代码上下文: struct stream_encoder *dcn301_stream_encoder_create(
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/dcn301/dcn301_resource.c` 的 `struct stream_encoder *dcn301_stream_encoder_create(` 上下文中将 `if (!enc1 || !vpg || !afmt) {` 调整为 `if (!enc1 || !vpg || !afmt || eng_id >= ARRAY_SIZE(stream_enc_regs)) {`。

## CVE-2024-26661
- Title: drm/amd/display: Add NULL test for 'timing generator' in 'dcn21_set_pipe()'
- Affected files: drivers/gpu/drm/amd/display/dc/hwss/dcn21/dcn21_hwseq.c
- Card: cards/CVE-2024-26661.md

- 补丁主题: drm/amd/display: Add NULL test for 'timing generator' in
- 代码上下文: void dcn21_set_abm_immediate_disable(struct pipe_ctx *pipe_ctx)
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/hwss/dcn21/dcn21_hwseq.c` 的 `void dcn21_set_abm_immediate_disable(struct pipe_ctx *pipe_ctx)` 上下文中调整 `set_pipe_ex()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/amd/display/dc/hwss/dcn21/dcn21_hwseq.c` 的 `void dcn21_set_abm_immediate_disable(struct pipe_ctx *pipe_ctx)` 上下文中将 `uint32_t otg_inst = pipe_ctx->stream_res.tg->inst;` 调整为 `struct timing_generator *tg = pipe_ctx->stream_res.tg;`。

## CVE-2024-26662
- Title: drm/amd/display: Fix 'panel_cntl' could be null in 'dcn21_set_backlight_level()'
- Affected files: drivers/gpu/drm/amd/display/dc/hwss/dcn21/dcn21_hwseq.c
- Card: cards/CVE-2024-26662.md

- 补丁主题: drm/amd/display: Fix 'panel_cntl' could be null in
- 代码上下文: bool dcn21_set_backlight_level(struct pipe_ctx *pipe_ctx,
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/hwss/dcn21/dcn21_hwseq.c` 的 `bool dcn21_set_backlight_level(struct pipe_ctx *pipe_ctx,` 上下文中调整 `set_pipe_ex()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/amd/display/dc/hwss/dcn21/dcn21_hwseq.c` 的 `bool dcn21_set_backlight_level(struct pipe_ctx *pipe_ctx,` 上下文中将 `if (abm != NULL) {` 调整为 `struct timing_generator *tg = pipe_ctx->stream_res.tg;`。

## CVE-2024-26663
- Title: tipc: Check the bearer type before calling tipc_udp_nl_bearer_add()
- Affected files: net/tipc/bearer.c
- Card: cards/CVE-2024-26663.md

- 补丁主题: tipc: Check the bearer type before calling tipc_udp_nl_bearer_add()
- 代码上下文: int tipc_nl_bearer_add(struct sk_buff *skb, struct genl_info *info)
- 建议落地动作:
  - 在 `net/tipc/bearer.c` 的 `int tipc_nl_bearer_add(struct sk_buff *skb, struct genl_info *info)` 上下文中新增 `if (b->media->type_id != TIPC_MEDIA_TYPE_UDP) {`。

## CVE-2024-26664
- Title: hwmon: (coretemp) Fix out-of-bounds memory access
- Affected files: drivers/hwmon/coretemp.c
- Card: cards/CVE-2024-26664.md

- 补丁主题: hwmon: (coretemp) Fix out-of-bounds memory access
- 代码上下文: static int create_core_data(struct platform_device *pdev, unsigned int cpu,
- 建议落地动作:
  - 在 `drivers/hwmon/coretemp.c` 的 `static int create_core_data(struct platform_device *pdev, unsigned int cpu,` 上下文中将 `index = ida_alloc(&pdata->ida, GFP_KERNEL);` 调整为 `index = ida_alloc_max(&pdata->ida, NUM_REAL_CORES - 1, GFP_KERNEL);`。

## CVE-2024-26665
- Title: tunnels: fix out of bounds access when building IPv6 PMTU error
- Affected files: net/ipv4/ip_tunnel_core.c
- Card: cards/CVE-2024-26665.md

- 补丁主题: tunnels: fix out of bounds access when building IPv6 PMTU error
- 代码上下文: static int iptunnel_pmtud_build_icmpv6(struct sk_buff *skb, int mtu)
- 建议落地动作:
  - 在 `net/ipv4/ip_tunnel_core.c` 的 `static int iptunnel_pmtud_build_icmpv6(struct sk_buff *skb, int mtu)` 上下文中将 `csum = csum_partial(icmp6h, len, 0);` 调整为 `csum = skb_checksum(skb, skb_transport_offset(skb), len, 0);`。

## CVE-2024-26666
- Title: wifi: mac80211: fix RCU use in TDLS fast-xmit
- Affected files: net/mac80211/tx.c
- Card: cards/CVE-2024-26666.md

- 补丁主题: wifi: mac80211: fix RCU use in TDLS fast-xmit
- 代码上下文: void ieee80211_check_fast_xmit(struct sta_info *sta)
- 建议落地动作:
  - 在 `net/mac80211/tx.c` 的 `void ieee80211_check_fast_xmit(struct sta_info *sta)` 上下文中调整 `memcpy()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/mac80211/tx.c` 的 `void ieee80211_check_fast_xmit(struct sta_info *sta)` 上下文中将 `if (WARN_ON_ONCE(!link))` 调整为 `rcu_read_lock();`。

## CVE-2024-26667
- Title: drm/msm/dpu: check for valid hw_pp in dpu_encoder_helper_phys_cleanup
- Affected files: drivers/gpu/drm/msm/disp/dpu1/dpu_encoder.c
- Card: cards/CVE-2024-26667.md

- 补丁主题: drm/msm/dpu: check for valid hw_pp in dpu_encoder_helper_phys_cleanup
- 代码上下文: void dpu_encoder_helper_phys_cleanup(struct dpu_encoder_phys *phys_enc)
- 建议落地动作:
  - 在 `drivers/gpu/drm/msm/disp/dpu1/dpu_encoder.c` 的 `void dpu_encoder_helper_phys_cleanup(struct dpu_encoder_phys *phys_enc)` 上下文中将 `if (phys_enc->hw_pp->merge_3d) {` 调整为 `if (phys_enc->hw_pp && phys_enc->hw_pp->merge_3d) {`。
  - 在 `drivers/gpu/drm/msm/disp/dpu1/dpu_encoder.c` 的 `void dpu_encoder_helper_phys_cleanup(struct dpu_encoder_phys *phys_enc)` 上下文中将 `if (phys_enc->hw_pp->merge_3d)` 调整为 `if (phys_enc->hw_pp && phys_enc->hw_pp->merge_3d)`。

## CVE-2024-26668
- Title: netfilter: nft_limit: reject configurations that cause integer overflow
- Affected files: net/netfilter/nft_limit.c
- Card: cards/CVE-2024-26668.md

- 补丁主题: netfilter: nft_limit: reject configurations that cause integer
- 代码上下文: static inline bool nft_limit_eval(struct nft_limit_priv *priv, u64 cost), static int nft_limit_init(struct nft_limit_priv *priv,
- 建议落地动作:
  - 在 `net/netfilter/nft_limit.c` 的 `static inline bool nft_limit_eval(struct nft_limit_priv *priv, u64 cost)` 上下文中将 `u64 unit, tokens;` 调整为 `u64 unit, tokens, rate_with_burst;`。
  - 在 `net/netfilter/nft_limit.c` 的 `static int nft_limit_init(struct nft_limit_priv *priv,` 上下文中将 `if (priv->rate + priv->burst < priv->rate)` 调整为 `if (check_add_overflow(priv->rate, priv->burst, &rate_with_burst))`。

## CVE-2024-26669
- Title: net/sched: flower: Fix chain template offload
- Affected files: include/net/sch_generic.h, net/sched/cls_api.c, net/sched/cls_flower.c
- Card: cards/CVE-2024-26669.md

- 补丁主题: net/sched: flower: Fix chain template offload
- 代码上下文: struct tcf_proto_ops {, tcf_block_playback_offloads(struct tcf_block *block, flow_setup_cb_t *cb,, static int tc_chain_tmplt_add(struct tcf_chain *chain, struct net *net,, static void fl_tmplt_destroy(void *tmplt_priv), static struct tcf_proto_ops cls_fl_ops __read_mostly = {
- 建议落地动作:
  - 在 `include/net/sch_generic.h` 的 `struct tcf_proto_ops {` 上下文中新增 `void (*tmplt_reoffload)(struct tcf_chain *chain,`。
  - 在 `net/sched/cls_api.c` 的 `tcf_block_playback_offloads(struct tcf_block *block, flow_setup_cb_t *cb,` 上下文中新增 `if (chain->tmplt_ops && add)`。
  - 在 `net/sched/cls_api.c` 的 `tcf_block_playback_offloads(struct tcf_block *block, flow_setup_cb_t *cb,` 上下文中新增 `if (chain->tmplt_ops && !add)`。
  - 在 `net/sched/cls_api.c` 的 `static int tc_chain_tmplt_add(struct tcf_chain *chain, struct net *net,` 上下文中将 `if (!ops->tmplt_create || !ops->tmplt_destroy || !ops->tmplt_dump) {` 调整为 `if (!ops->tmplt_create || !ops->tmplt_destroy || !ops->tmplt_dump ||`。

## CVE-2024-26670
- Title: arm64: entry: fix ARM64_WORKAROUND_SPECULATIVE_UNPRIV_LOAD
- Affected files: arch/arm64/kernel/entry.S
- Card: cards/CVE-2024-26670.md

- 补丁主题: arm64: entry: fix ARM64_WORKAROUND_SPECULATIVE_UNPRIV_LOAD
- 代码上下文: alternative_else_nop_endif
- 建议落地动作:
  - 在 `arch/arm64/kernel/entry.S` 的 `alternative_else_nop_endif` 上下文中将 `alternative_if ARM64_WORKAROUND_SPECULATIVE_UNPRIV_LOAD` 调整为 `alternative_insn "b .L_skip_tramp_exit_\@", nop, ARM64_UNMAP_KERNEL_AT_EL0`。
  - 在 `arch/arm64/kernel/entry.S` 的 `alternative_else_nop_endif` 上下文中新增 `.L_skip_tramp_exit_\@:`。

## CVE-2024-26671
- Title: blk-mq: fix IO hang from sbitmap wakeup race
- Affected files: block/blk-mq.c
- Card: cards/CVE-2024-26671.md

- 补丁主题: blk-mq: fix IO hang from sbitmap wakeup race
- 代码上下文: static bool blk_mq_mark_tag_wait(struct blk_mq_hw_ctx *hctx,
- 建议落地动作:
  - 在 `block/blk-mq.c` 的 `static bool blk_mq_mark_tag_wait(struct blk_mq_hw_ctx *hctx,` 上下文中新增 `* Add one explicit barrier since blk_mq_get_driver_tag() may`。

## CVE-2024-26672
- Title: drm/amdgpu: Fix variable 'mca_funcs' dereferenced before NULL check in 'amdgpu_mca_smu_get_mca_entry()'
- Affected files: drivers/gpu/drm/amd/amdgpu/amdgpu_mca.c
- Card: cards/CVE-2024-26672.md

- 补丁主题: drm/amdgpu: Fix variable 'mca_funcs' dereferenced before NULL check
- 代码上下文: int amdgpu_mca_smu_get_mca_entry(struct amdgpu_device *adev, enum amdgpu_mca_err
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/amdgpu/amdgpu_mca.c` 的 `int amdgpu_mca_smu_get_mca_entry(struct amdgpu_device *adev, enum amdgpu_mca_err` 上下文中调整 `mca_get_mca_entry()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/amd/amdgpu/amdgpu_mca.c` 的 `int amdgpu_mca_smu_get_mca_entry(struct amdgpu_device *adev, enum amdgpu_mca_err` 上下文中新增 `if (!mca_funcs || !mca_funcs->mca_get_mca_entry)`。
  - 在 `drivers/gpu/drm/amd/amdgpu/amdgpu_mca.c` 的 `int amdgpu_mca_smu_get_mca_entry(struct amdgpu_device *adev, enum amdgpu_mca_err` 上下文中将 `if (mca_funcs && mca_funcs->mca_get_mca_entry)` 调整为 `return mca_funcs->mca_get_mca_entry(adev, type, idx, entry);`。

## CVE-2024-26673
- Title: netfilter: nft_ct: sanitize layer 3 and 4 protocol number in custom expectations
- Affected files: net/netfilter/nft_ct.c
- Card: cards/CVE-2024-26673.md

- 补丁主题: netfilter: nft_ct: sanitize layer 3 and 4 protocol number in custom
- 代码上下文: static int nft_ct_expect_obj_init(const struct nft_ctx *ctx,
- 建议落地动作:
  - 在 `net/netfilter/nft_ct.c` 的 `static int nft_ct_expect_obj_init(const struct nft_ctx *ctx,` 上下文中新增 `switch (priv->l3num) {`。

## CVE-2024-26674
- Title: x86/lib: Revert to _ASM_EXTABLE_UA() for {get,put}_user() fixups
- Affected files: arch/x86/lib/getuser.S, arch/x86/lib/putuser.S
- Card: cards/CVE-2024-26674.md

- 补丁主题: x86/lib: Revert to _ASM_EXTABLE_UA() for {get,put}_user() fixups
- 代码上下文: SYM_CODE_END(__get_user_8_handle_exception), SYM_CODE_START_LOCAL(__put_user_handle_exception)
- 建议落地动作:
  - 在 `arch/x86/lib/getuser.S` 的 `SYM_CODE_END(__get_user_8_handle_exception)` 上下文中将 `_ASM_EXTABLE(1b, __get_user_handle_exception)` 调整为 `_ASM_EXTABLE_UA(1b, __get_user_handle_exception)`。
  - 在 `arch/x86/lib/putuser.S` 的 `SYM_CODE_START_LOCAL(__put_user_handle_exception)` 上下文中将 `_ASM_EXTABLE(1b, __put_user_handle_exception)` 调整为 `_ASM_EXTABLE_UA(1b, __put_user_handle_exception)`。

## CVE-2024-26675
- Title: ppp_async: limit MRU to 64K
- Affected files: drivers/net/ppp/ppp_async.c
- Card: cards/CVE-2024-26675.md

- 补丁主题: ppp_async: limit MRU to 64K
- 代码上下文: ppp_async_ioctl(struct ppp_channel *chan, unsigned int cmd, unsigned long arg)
- 建议落地动作:
  - 在 `drivers/net/ppp/ppp_async.c` 的 `ppp_async_ioctl(struct ppp_channel *chan, unsigned int cmd, unsigned long arg)` 上下文中新增 `if (val > U16_MAX) {`。

## CVE-2024-26676
- Title: af_unix: Call kfree_skb() for dead unix_(sk)->oob_skb in GC.
- Affected files: net/unix/garbage.c
- Card: cards/CVE-2024-26676.md

- 补丁主题: af_unix: Call kfree_skb() for dead unix_(sk)->oob_skb in GC.
- 代码上下文: void unix_gc(void)
- 建议落地动作:
  - 在 `net/unix/garbage.c` 的 `void unix_gc(void)` 上下文中新增 `#if IS_ENABLED(CONFIG_AF_UNIX_OOB)`。

## CVE-2024-26677
- Title: rxrpc: Fix delayed ACKs to not set the reference serial number
- Affected files: net/rxrpc/ar-internal.h, net/rxrpc/call_event.c
- Card: cards/CVE-2024-26677.md

- 补丁主题: rxrpc: Fix delayed ACKs to not set the reference serial number
- 代码上下文: struct rxrpc_call {, void rxrpc_propose_delay_ACK(struct rxrpc_call *call, rxrpc_serial_t serial,, static void rxrpc_send_initial_ping(struct rxrpc_call *call), bool rxrpc_input_call_event(struct rxrpc_call *call, struct sk_buff *skb)
- 建议落地动作:
  - 在 `net/rxrpc/ar-internal.h` 的 `struct rxrpc_call {` 上下文中移除 `rxrpc_serial_t ackr_serial; /* serial of packet being ACK'd */`。
  - 在 `net/rxrpc/call_event.c` 的 `void rxrpc_propose_delay_ACK(struct rxrpc_call *call, rxrpc_serial_t serial,` 上下文中移除 `call->ackr_serial = serial;`。
  - 在 `net/rxrpc/call_event.c` 的 `static void rxrpc_send_initial_ping(struct rxrpc_call *call)` 上下文中移除 `rxrpc_serial_t ackr_serial;`。
  - 在 `net/rxrpc/call_event.c` 的 `bool rxrpc_input_call_event(struct rxrpc_call *call, struct sk_buff *skb)` 上下文中将 `ackr_serial = xchg(&call->ackr_serial, 0);` 调整为 `rxrpc_send_ACK(call, RXRPC_ACK_DELAY, 0,`。

## CVE-2024-26678
- Title: x86/efistub: Use 1:1 file:memory mapping for PE/COFF .compat section
- Affected files: arch/x86/boot/header.S, arch/x86/boot/setup.ld
- Card: cards/CVE-2024-26678.md

- 补丁主题: x86/efistub: Use 1:1 file:memory mapping for PE/COFF .compat section
- 代码上下文: extra_header_fields:, section_table:, SECTIONS
- 建议落地动作:
  - 在 `arch/x86/boot/header.S` 的 `extra_header_fields:` 上下文中将 `.long setup_size + ZO__end + pecompat_vsize` 调整为 `.long setup_size + ZO__end # SizeOfImage`。
  - 在 `arch/x86/boot/header.S` 的 `section_table:` 上下文中将 `.long setup_size - salign # VirtualSize` 调整为 `.long pecompat_fstart - salign # VirtualSize`。
  - 在 `arch/x86/boot/header.S` 的 `section_table:` 上下文中将 `.long 8 # VirtualSize` 调整为 `.long pecompat_fsize # VirtualSize`。
  - 在 `arch/x86/boot/header.S` 的 `section_table:` 上下文中将 `.balign falign` 调整为 `.balign salign`。

## CVE-2024-26679
- Title: inet: read sk->sk_family once in inet_recv_error()
- Affected files: net/ipv4/af_inet.c
- Card: cards/CVE-2024-26679.md

- 补丁主题: inet: read sk->sk_family once in inet_recv_error()
- 代码上下文: EXPORT_SYMBOL(inet_current_timestamp);
- 建议落地动作:
  - 在 `net/ipv4/af_inet.c` 的 `EXPORT_SYMBOL(inet_current_timestamp);` 上下文中将 `if (sk->sk_family == AF_INET)` 调整为 `unsigned int family = READ_ONCE(sk->sk_family);`。

## CVE-2024-26680
- Title: net: atlantic: Fix DMA mapping for PTP hwts ring
- Affected files: drivers/net/ethernet/aquantia/atlantic/aq_ptp.c, drivers/net/ethernet/aquantia/atlantic/aq_ring.c, drivers/net/ethernet/aquantia/atlantic/aq_ring.h
- Card: cards/CVE-2024-26680.md

- 补丁主题: net: atlantic: Fix DMA mapping for PTP hwts ring
- 代码上下文: int aq_ptp_ring_alloc(struct aq_nic_s *aq_nic), void aq_ptp_ring_free(struct aq_nic_s *aq_nic), void aq_ring_free(struct aq_ring_s *self), int aq_ring_rx_fill(struct aq_ring_s *self);
- 建议落地动作:
  - 在 `drivers/net/ethernet/aquantia/atlantic/aq_ptp.c` 的 `int aq_ptp_ring_alloc(struct aq_nic_s *aq_nic)` 上下文中将 `aq_ring_free(&aq_ptp->hwts_rx);` 调整为 `aq_ring_hwts_rx_free(&aq_ptp->hwts_rx);`。
  - 在 `drivers/net/ethernet/aquantia/atlantic/aq_ptp.c` 的 `void aq_ptp_ring_free(struct aq_nic_s *aq_nic)` 上下文中将 `aq_ring_free(&aq_ptp->hwts_rx);` 调整为 `aq_ring_hwts_rx_free(&aq_ptp->hwts_rx);`。
  - 在 `drivers/net/ethernet/aquantia/atlantic/aq_ring.c` 的 `void aq_ring_free(struct aq_ring_s *self)` 上下文中新增 `void aq_ring_hwts_rx_free(struct aq_ring_s *self)`。
  - 在 `drivers/net/ethernet/aquantia/atlantic/aq_ring.h` 的 `int aq_ring_rx_fill(struct aq_ring_s *self);` 上下文中新增 `void aq_ring_hwts_rx_free(struct aq_ring_s *self);`。

## CVE-2024-26681
- Title: netdevsim: avoid potential loop in nsim_dev_trap_report_work()
- Affected files: drivers/net/netdevsim/dev.c
- Card: cards/CVE-2024-26681.md

- 补丁主题: netdevsim: avoid potential loop in nsim_dev_trap_report_work()
- 代码上下文: static void nsim_dev_trap_report_work(struct work_struct *work)
- 建议落地动作:
  - 在 `drivers/net/netdevsim/dev.c` 的 `static void nsim_dev_trap_report_work(struct work_struct *work)` 上下文中将 `/* For each running port and enabled packet trap, generate a UDP` 调整为 `schedule_delayed_work(&nsim_dev->trap_data->trap_report_dw, 1);`。

## CVE-2024-26682
- Title: wifi: mac80211: improve CSA/ECSA connection refusal
- Affected files: net/mac80211/mlme.c
- Card: cards/CVE-2024-26682.md

- 补丁主题: wifi: mac80211: improve CSA/ECSA connection refusal
- 代码上下文: out_err:, int ieee80211_mgd_auth(struct ieee80211_sub_if_data *sdata,, int ieee80211_mgd_assoc(struct ieee80211_sub_if_data *sdata,
- 建议落地动作:
  - 在 `net/mac80211/mlme.c` 中调整 `rcu_read_lock()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/mac80211/mlme.c` 的 `out_err:` 上下文中新增 `static bool ieee80211_mgd_csa_present(struct ieee80211_sub_if_data *sdata,`。
  - 在 `net/mac80211/mlme.c` 的 `int ieee80211_mgd_auth(struct ieee80211_sub_if_data *sdata,` 上下文中移除 `const struct element *csa_elem, *ecsa_elem;`。
  - 在 `net/mac80211/mlme.c` 的 `int ieee80211_mgd_auth(struct ieee80211_sub_if_data *sdata,` 上下文中将 `rcu_read_lock();` 调整为 `if (ieee80211_mgd_csa_in_process(sdata, req->bss)) {`。

## CVE-2024-26683
- Title: wifi: cfg80211: detect stuck ECSA element in probe resp
- Affected files: include/net/cfg80211.h, net/wireless/scan.c
- Card: cards/CVE-2024-26683.md

- 补丁主题: wifi: cfg80211: detect stuck ECSA element in probe resp
- 代码上下文: struct cfg80211_bss_ies {, struct cfg80211_bss {, static void cfg80211_update_hidden_bsses(struct cfg80211_internal_bss *known,, cfg80211_update_known_bss(struct cfg80211_registered_device *rdev,
- 建议落地动作:
  - 在 `include/net/cfg80211.h` 的 `struct cfg80211_bss_ies {` 上下文中新增 `* @proberesp_ecsa_stuck: ECSA element is stuck in the Probe Response frame,`。
  - 在 `include/net/cfg80211.h` 的 `struct cfg80211_bss {` 上下文中新增 `u8 proberesp_ecsa_stuck:1;`。
  - 在 `net/wireless/scan.c` 的 `static void cfg80211_update_hidden_bsses(struct cfg80211_internal_bss *known,` 上下文中新增 `static void cfg80211_check_stuck_ecsa(struct cfg80211_registered_device *rdev,`。
  - 在 `net/wireless/scan.c` 的 `cfg80211_update_known_bss(struct cfg80211_registered_device *rdev,` 上下文中将 `if (old)` 调整为 `if (old) {`。

## CVE-2024-26684
- Title: net: stmmac: xgmac: fix handling of DPP safety error for DMA channels
- Affected files: drivers/net/ethernet/stmicro/stmmac/common.h, drivers/net/ethernet/stmicro/stmmac/dwxgmac2.h, drivers/net/ethernet/stmicro/stmmac/dwxgmac2_core.c
- Card: cards/CVE-2024-26684.md

- 补丁主题: net: stmmac: xgmac: fix handling of DPP safety error for DMA channels
- 代码上下文: struct stmmac_safety_stats {, static const struct dwxgmac3_error_desc dwxgmac3_dma_errors[32]= {, static void dwxgmac3_handle_dma_err(struct net_device *ndev,, static int dwxgmac3_safety_feat_config(void __iomem *ioaddr, unsigned int asp), static int dwxgmac3_safety_feat_irq_status(struct net_device *ndev,, static const struct dwxgmac3_error {
- 建议落地动作:
  - 在 `drivers/net/ethernet/stmicro/stmmac/common.h` 的 `struct stmmac_safety_stats {` 上下文中新增 `unsigned long dma_dpp_errors[32];`。
  - 在 `drivers/net/ethernet/stmicro/stmmac/dwxgmac2.h` 的 `global` 上下文中新增 `#define XGMAC_MTL_DPP_CONTROL 0x000010e0`。
  - 在 `drivers/net/ethernet/stmicro/stmmac/dwxgmac2.h` 的 `global` 上下文中新增 `#define XGMAC_DMA_DPP_INT_STATUS 0x00003074`。
  - 在 `drivers/net/ethernet/stmicro/stmmac/dwxgmac2_core.c` 的 `static const struct dwxgmac3_error_desc dwxgmac3_dma_errors[32]= {` 上下文中新增 `static const char * const dpp_rx_err = "Read Rx Descriptor Parity checker Error";`。

## CVE-2024-26685
- Title: nilfs2: fix potential bug in end_buffer_async_write
- Affected files: fs/nilfs2/segment.c
- Card: cards/CVE-2024-26685.md

- 补丁主题: nilfs2: fix potential bug in end_buffer_async_write
- 代码上下文: static void nilfs_segctor_prepare_write(struct nilfs_sc_info *sci), static void nilfs_abort_logs(struct list_head *logs, int err), static void nilfs_segctor_complete_write(struct nilfs_sc_info *sci)
- 建议落地动作:
  - 在 `fs/nilfs2/segment.c` 中调整 `set_buffer_async_write()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `fs/nilfs2/segment.c` 的 `static void nilfs_segctor_prepare_write(struct nilfs_sc_info *sci)` 上下文中移除 `set_buffer_async_write(bh);`。
  - 在 `fs/nilfs2/segment.c` 的 `static void nilfs_segctor_prepare_write(struct nilfs_sc_info *sci)` 上下文中新增 `set_buffer_async_write(bh);`。
  - 在 `fs/nilfs2/segment.c` 的 `static void nilfs_abort_logs(struct list_head *logs, int err)` 上下文中移除 `clear_buffer_async_write(bh);`。

## CVE-2024-26686
- Title: fs/proc: do_task_stat: use sig->stats_lock to gather the threads/children stats
- Affected files: fs/proc/array.c
- Card: cards/CVE-2024-26686.md

- 补丁主题: fs/proc: do_task_stat: use sig->stats_lock to gather the
- 代码上下文: static int do_task_stat(struct seq_file *m, struct pid_namespace *ns,
- 建议落地动作:
  - 在 `fs/proc/array.c` 的 `static int do_task_stat(struct seq_file *m, struct pid_namespace *ns,` 上下文中调整 `READ_ONCE()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `fs/proc/array.c` 的 `static int do_task_stat(struct seq_file *m, struct pid_namespace *ns,` 上下文中将 `unsigned long cmin_flt = 0, cmaj_flt = 0;` 调整为 `unsigned long cmin_flt, cmaj_flt, min_flt, maj_flt;`。
  - 在 `fs/proc/array.c` 的 `static int do_task_stat(struct seq_file *m, struct pid_namespace *ns,` 上下文中移除 `cutime = cstime = 0;`。
  - 在 `fs/proc/array.c` 的 `static int do_task_stat(struct seq_file *m, struct pid_namespace *ns,` 上下文中调整 `READ_ONCE()` 的调用位置，使其与新的初始化顺序保持一致。

## CVE-2024-26687
- Title: xen/events: close evtchn after mapping cleanup
- Affected files: drivers/xen/events/events_base.c
- Card: cards/CVE-2024-26687.md

- 补丁主题: xen/events: close evtchn after mapping cleanup
- 代码上下文: static void shutdown_pirq(struct irq_data *data), static void __unbind_from_irq(unsigned int irq)
- 建议落地动作:
  - 在 `drivers/xen/events/events_base.c` 中调整 `xen_evtchn_close()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/xen/events/events_base.c` 的 `static void shutdown_pirq(struct irq_data *data)` 上下文中调整 `xen_evtchn_close()` 的调用位置，使其与新的初始化顺序保持一致。
  - 在 `drivers/xen/events/events_base.c` 的 `static void __unbind_from_irq(unsigned int irq)` 上下文中移除 `xen_evtchn_close(evtchn);`。
  - 在 `drivers/xen/events/events_base.c` 的 `static void __unbind_from_irq(unsigned int irq)` 上下文中新增 `xen_evtchn_close(evtchn);`。

## CVE-2024-26688
- Title: fs,hugetlb: fix NULL pointer dereference in hugetlbs_fill_super
- Affected files: fs/hugetlbfs/inode.c
- Card: cards/CVE-2024-26688.md

- 补丁主题: fs,hugetlb: fix NULL pointer dereference in hugetlbs_fill_super
- 代码上下文: static int hugetlbfs_parse_param(struct fs_context *fc, struct fs_parameter *par
- 建议落地动作:
  - 在 `fs/hugetlbfs/inode.c` 的 `static int hugetlbfs_parse_param(struct fs_context *fc, struct fs_parameter *par` 上下文中新增 `struct hstate *h;`。
  - 在 `fs/hugetlbfs/inode.c` 的 `static int hugetlbfs_parse_param(struct fs_context *fc, struct fs_parameter *par` 上下文中将 `ctx->hstate = size_to_hstate(ps);` 调整为 `h = size_to_hstate(ps);`。

## CVE-2024-26689
- Title: ceph: prevent use-after-free in encode_cap_msg()
- Affected files: fs/ceph/caps.c
- Card: cards/CVE-2024-26689.md

- 补丁主题: ceph: prevent use-after-free in encode_cap_msg()
- 代码上下文: static void __prep_cap(struct cap_msg_args *arg, struct ceph_cap *cap,, static void __send_cap(struct cap_msg_args *arg, struct ceph_inode_info *ci)
- 建议落地动作:
  - 在 `fs/ceph/caps.c` 的 `static void __prep_cap(struct cap_msg_args *arg, struct ceph_cap *cap,` 上下文中将 `arg->xattr_buf = ci->i_xattrs.blob;` 调整为 `arg->xattr_buf = ceph_buffer_get(ci->i_xattrs.blob);`。
  - 在 `fs/ceph/caps.c` 的 `static void __send_cap(struct cap_msg_args *arg, struct ceph_inode_info *ci)` 上下文中新增 `ceph_buffer_put(arg->xattr_buf);`。

## CVE-2024-26690
- Title: net: stmmac: protect updates of 64-bit statistics counters
- Affected files: drivers/net/ethernet/stmicro/stmmac/common.h, drivers/net/ethernet/stmicro/stmmac/dwmac-sun8i.c, drivers/net/ethernet/stmicro/stmmac/dwmac4_lib.c, drivers/net/ethernet/stmicro/stmmac/dwmac_lib.c, drivers/net/ethernet/stmicro/stmmac/dwxgmac2_dma.c, drivers/net/ethernet/stmicro/stmmac/stmmac_ethtool.c, drivers/net/ethernet/stmicro/stmmac/stmmac_main.c
- Card: cards/CVE-2024-26690.md

- 补丁主题: net: stmmac: protect updates of 64-bit statistics counters
- 代码上下文: struct stmmac_extra_stats {, static int sun8i_dwmac_dma_interrupt(struct stmmac_priv *priv,, int dwmac4_dma_interrupt(struct stmmac_priv *priv, void __iomem *ioaddr,, static void show_rx_process_state(unsigned int status), int dwmac_dma_interrupt(struct stmmac_priv *priv, void __iomem *ioaddr,, static int dwxgmac2_dma_interrupt(struct stmmac_priv *priv,, stmmac_set_pauseparam(struct net_device *netdev,, static void stmmac_get_ethtool_stats(struct net_device *dev,
- 建议落地动作:
  - 在 `drivers/net/ethernet/stmicro/stmmac/common.h` 的 `global` 上下文中将 `u64 tx_bytes;` 调整为 `struct stmmac_q_tx_stats {`。
  - 在 `drivers/net/ethernet/stmicro/stmmac/common.h` 的 `struct stmmac_extra_stats {` 上下文中新增 `struct stmmac_pcpu_stats __percpu *pcpu_stats;`。
  - 在 `drivers/net/ethernet/stmicro/stmmac/dwmac-sun8i.c` 的 `static int sun8i_dwmac_dma_interrupt(struct stmmac_priv *priv,` 上下文中将 `struct stmmac_rxq_stats *rxq_stats = &priv->xstats.rxq_stats[chan];` 调整为 `struct stmmac_pcpu_stats *stats = this_cpu_ptr(priv->xstats.pcpu_stats);`。
  - 在 `drivers/net/ethernet/stmicro/stmmac/dwmac-sun8i.c` 的 `static int sun8i_dwmac_dma_interrupt(struct stmmac_priv *priv,` 上下文中将 `u64_stats_update_begin(&txq_stats->syncp);` 调整为 `u64_stats_update_begin(&stats->syncp);`。

## CVE-2024-26691
- Title: KVM: arm64: Fix circular locking dependency
- Affected files: arch/arm64/kvm/pkvm.c
- Card: cards/CVE-2024-26691.md

- 补丁主题: KVM: arm64: Fix circular locking dependency
- 代码上下文: void __init kvm_hyp_reserve(void), static int __pkvm_create_hyp_vm(struct kvm *host_kvm), int pkvm_create_hyp_vm(struct kvm *host_kvm)
- 建议落地动作:
  - 在 `arch/arm64/kvm/pkvm.c` 中调整 `WARN_ON()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `arch/arm64/kvm/pkvm.c` 的 `void __init kvm_hyp_reserve(void)` 上下文中新增 `static void __pkvm_destroy_hyp_vm(struct kvm *host_kvm)`。
  - 在 `arch/arm64/kvm/pkvm.c` 的 `static int __pkvm_create_hyp_vm(struct kvm *host_kvm)` 上下文中将 `pkvm_destroy_hyp_vm(host_kvm);` 调整为 `__pkvm_destroy_hyp_vm(host_kvm);`。
  - 在 `arch/arm64/kvm/pkvm.c` 的 `int pkvm_create_hyp_vm(struct kvm *host_kvm)` 上下文中将 `mutex_lock(&host_kvm->lock);` 调整为 `mutex_lock(&host_kvm->arch.config_lock);`。

## CVE-2024-26692
- Title: smb: Fix regression in writes when non-standard maximum write size negotiated
- Affected files: fs/smb/client/connect.c, fs/smb/client/fs_context.c
- Card: cards/CVE-2024-26692.md

- 补丁主题: smb: Fix regression in writes when non-standard maximum write size
- 代码上下文: int cifs_mount_get_tcon(struct cifs_mount_ctx *mnt_ctx), static int smb3_fs_context_parse_param(struct fs_context *fc,
- 建议落地动作:
  - 在 `fs/smb/client/connect.c` 的 `int cifs_mount_get_tcon(struct cifs_mount_ctx *mnt_ctx)` 上下文中将 `(cifs_sb->ctx->wsize > server->ops->negotiate_wsize(tcon, ctx)))` 调整为 `(cifs_sb->ctx->wsize > server->ops->negotiate_wsize(tcon, ctx))) {`。
  - 在 `fs/smb/client/fs_context.c` 的 `static int smb3_fs_context_parse_param(struct fs_context *fc,` 上下文中新增 `if (ctx->wsize % PAGE_SIZE != 0) {`。

## CVE-2024-26693
- Title: wifi: iwlwifi: mvm: fix a crash when we run out of stations
- Affected files: drivers/net/wireless/intel/iwlwifi/mvm/mac80211.c, drivers/net/wireless/intel/iwlwifi/mvm/rxmq.c
- Card: cards/CVE-2024-26693.md

- 补丁主题: wifi: iwlwifi: mvm: fix a crash when we run out of stations
- 代码上下文: iwl_mvm_sta_state_notexist_to_none(struct iwl_mvm *mvm,, static bool iwl_mvm_is_dup(struct ieee80211_sta *sta, int queue,
- 建议落地动作:
  - 在 `drivers/net/wireless/intel/iwlwifi/mvm/mac80211.c` 的 `iwl_mvm_sta_state_notexist_to_none(struct iwl_mvm *mvm,` 上下文中新增 `if (ret)`。
  - 在 `drivers/net/wireless/intel/iwlwifi/mvm/rxmq.c` 的 `static bool iwl_mvm_is_dup(struct ieee80211_sta *sta, int queue,` 上下文中新增 `if (WARN_ON_ONCE(!mvm_sta->dup_data))`。

## CVE-2024-26694
- Title: wifi: iwlwifi: fix double-free bug
- Affected files: drivers/net/wireless/intel/iwlwifi/iwl-drv.c
- Card: cards/CVE-2024-26694.md

- 补丁主题: wifi: iwlwifi: fix double-free bug
- 代码上下文: static void iwl_dealloc_ucode(struct iwl_drv *drv)
- 建议落地动作:
  - 在 `drivers/net/wireless/intel/iwlwifi/iwl-drv.c` 的 `static void iwl_dealloc_ucode(struct iwl_drv *drv)` 上下文中新增 `drv->trans->dbg.pc_data = NULL;`。

## CVE-2024-26695
- Title: crypto: ccp - Fix null pointer dereference in __sev_platform_shutdown_locked
- Affected files: drivers/crypto/ccp/sev-dev.c
- Card: cards/CVE-2024-26695.md

- 补丁主题: crypto: ccp - Fix null pointer dereference in
- 代码上下文: EXPORT_SYMBOL_GPL(sev_platform_init);
- 建议落地动作:
  - 在 `drivers/crypto/ccp/sev-dev.c` 的 `EXPORT_SYMBOL_GPL(sev_platform_init);` 上下文中将 `struct sev_device *sev = psp_master->sev_data;` 调整为 `struct psp_device *psp = psp_master;`。

## CVE-2024-26696
- Title: nilfs2: fix hang in nilfs_lookup_dirty_data_buffers()
- Affected files: fs/nilfs2/file.c
- Card: cards/CVE-2024-26696.md

- 补丁主题: nilfs2: fix hang in nilfs_lookup_dirty_data_buffers()
- 代码上下文: static vm_fault_t nilfs_page_mkwrite(struct vm_fault *vmf)
- 建议落地动作:
  - 在 `fs/nilfs2/file.c` 的 `static vm_fault_t nilfs_page_mkwrite(struct vm_fault *vmf)` 上下文中将 `wait_for_stable_page(page);` 调整为 `* Since checksumming including data blocks is performed to determine`。

## CVE-2024-26697
- Title: nilfs2: fix data corruption in dsync block recovery for small block sizes
- Affected files: fs/nilfs2/recovery.c
- Card: cards/CVE-2024-26697.md

- 补丁主题: nilfs2: fix data corruption in dsync block recovery for small block
- 代码上下文: static int nilfs_prepare_segment_for_recovery(struct the_nilfs *nilfs,, static int nilfs_recovery_copy_block(struct the_nilfs *nilfs,, static int nilfs_recover_dsync_blocks(struct the_nilfs *nilfs,
- 建议落地动作:
  - 在 `fs/nilfs2/recovery.c` 的 `static int nilfs_prepare_segment_for_recovery(struct the_nilfs *nilfs,` 上下文中将 `struct page *page)` 调整为 `loff_t pos, struct page *page)`。
  - 在 `fs/nilfs2/recovery.c` 的 `static int nilfs_recovery_copy_block(struct the_nilfs *nilfs,` 上下文中将 `memcpy(kaddr + bh_offset(bh_org), bh_org->b_data, bh_org->b_size);` 调整为 `memcpy(kaddr + from, bh_org->b_data, bh_org->b_size);`。
  - 在 `fs/nilfs2/recovery.c` 的 `static int nilfs_recover_dsync_blocks(struct the_nilfs *nilfs,` 上下文中将 `err = nilfs_recovery_copy_block(nilfs, rb, page);` 调整为 `err = nilfs_recovery_copy_block(nilfs, rb, pos, page);`。

## CVE-2024-26698
- Title: hv_netvsc: Fix race condition between netvsc_probe and netvsc_remove
- Affected files: drivers/net/hyperv/netvsc.c
- Card: cards/CVE-2024-26698.md

- 补丁主题: hv_netvsc: Fix race condition between netvsc_probe and netvsc_remove
- 代码上下文: void netvsc_device_remove(struct hv_device *device)
- 建议落地动作:
  - 在 `drivers/net/hyperv/netvsc.c` 的 `void netvsc_device_remove(struct hv_device *device)` 上下文中调整 `napi_disable()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/net/hyperv/netvsc.c` 的 `void netvsc_device_remove(struct hv_device *device)` 上下文中将 `napi_disable(&net_device->chan_table[i].napi);` 调整为 `/* only disable enabled NAPI channel */`。

## CVE-2024-26699
- Title: drm/amd/display: Fix array-index-out-of-bounds in dcn35_clkmgr
- Affected files: drivers/gpu/drm/amd/display/dc/clk_mgr/dcn35/dcn35_clk_mgr.c
- Card: cards/CVE-2024-26699.md

- 补丁主题: drm/amd/display: Fix array-index-out-of-bounds in dcn35_clkmgr
- 代码上下文: static void dcn35_clk_mgr_helper_populate_bw_params(struct clk_mgr_internal *clk
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/clk_mgr/dcn35/dcn35_clk_mgr.c` 的 `static void dcn35_clk_mgr_helper_populate_bw_params(struct clk_mgr_internal *clk` 上下文中将 `for (i = 0; i < clock_table->NumMemPstatesEnabled; i++) {` 调整为 `uint32_t num_memps, num_fclk, num_dcfclk;`。
  - 在 `drivers/gpu/drm/amd/display/dc/clk_mgr/dcn35/dcn35_clk_mgr.c` 的 `static void dcn35_clk_mgr_helper_populate_bw_params(struct clk_mgr_internal *clk` 上下文中将 `for (i = 0; i < clock_table->NumMemPstatesEnabled; i++) {` 调整为 `for (i = 0; i < num_memps; i++) {`。
  - 在 `drivers/gpu/drm/amd/display/dc/clk_mgr/dcn35/dcn35_clk_mgr.c` 的 `static void dcn35_clk_mgr_helper_populate_bw_params(struct clk_mgr_internal *clk` 上下文中将 `max_fclk = find_max_clk_value(clock_table->FclkClocks_Freq, clock_table->NumFclkLevelsEnabled);` 调整为 `num_fclk = (clock_table->NumFclkLevelsEnabled > NUM_FCLK_DPM_LEVELS) ? NUM_FCLK_DPM_LEVELS :`。

## CVE-2024-26700
- Title: drm/amd/display: Fix MST Null Ptr for RV
- Affected files: drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c
- Card: cards/CVE-2024-26700.md

- 补丁主题: drm/amd/display: Fix MST Null Ptr for RV
- 代码上下文: static int amdgpu_dm_atomic_check(struct drm_device *dev,
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c` 的 `static int amdgpu_dm_atomic_check(struct drm_device *dev,` 上下文中调整 `compute_mst_dsc_configs_for_state()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c` 的 `static int amdgpu_dm_atomic_check(struct drm_device *dev,` 上下文中将 `ret = compute_mst_dsc_configs_for_state(state, dm_state->context, vars);` 调整为 `if (dc_resource_is_dsc_encoding_supported(dc)) {`。

## CVE-2024-26702
- Title: iio: magnetometer: rm3100: add boundary check for the value read from RM3100_REG_TMRC
- Affected files: drivers/iio/magnetometer/rm3100-core.c
- Card: cards/CVE-2024-26702.md

- 补丁主题: iio: magnetometer: rm3100: add boundary check for the value read from
- 代码上下文: int rm3100_common_probe(struct device *dev, struct regmap *regmap, int irq)
- 建议落地动作:
  - 在 `drivers/iio/magnetometer/rm3100-core.c` 的 `int rm3100_common_probe(struct device *dev, struct regmap *regmap, int irq)` 上下文中新增 `int samp_rate_index;`。
  - 在 `drivers/iio/magnetometer/rm3100-core.c` 的 `int rm3100_common_probe(struct device *dev, struct regmap *regmap, int irq)` 上下文中将 `data->conversion_time = rm3100_samp_rates[tmp - RM3100_TMRC_OFFSET][2]` 调整为 `samp_rate_index = tmp - RM3100_TMRC_OFFSET;`。

## CVE-2024-26703
- Title: tracing/timerlat: Move hrtimer_init to timerlat_fd open()
- Affected files: kernel/trace/trace_osnoise.c
- Card: cards/CVE-2024-26703.md

- 补丁主题: tracing/timerlat: Move hrtimer_init to timerlat_fd open()
- 代码上下文: static int timerlat_fd_open(struct inode *inode, struct file *file), timerlat_fd_read(struct file *file, char __user *ubuf, size_t count,
- 建议落地动作:
  - 在 `kernel/trace/trace_osnoise.c` 中调整 `hrtimer_init()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `kernel/trace/trace_osnoise.c` 的 `static int timerlat_fd_open(struct inode *inode, struct file *file)` 上下文中新增 `hrtimer_init(&tlat->timer, CLOCK_MONOTONIC, HRTIMER_MODE_ABS_PINNED_HARD);`。
  - 在 `kernel/trace/trace_osnoise.c` 的 `timerlat_fd_read(struct file *file, char __user *ubuf, size_t count,` 上下文中移除 `hrtimer_init(&tlat->timer, CLOCK_MONOTONIC, HRTIMER_MODE_ABS_PINNED_HARD);`。

## CVE-2024-26704
- Title: ext4: fix double-free of blocks due to wrong extents moved_len
- Affected files: fs/ext4/move_extent.c
- Card: cards/CVE-2024-26704.md

- 补丁主题: ext4: fix double-free of blocks due to wrong extents moved_len
- 代码上下文: ext4_move_extents(struct file *o_filp, struct file *d_filp, __u64 orig_blk,
- 建议落地动作:
  - 在 `fs/ext4/move_extent.c` 的 `ext4_move_extents(struct file *o_filp, struct file *d_filp, __u64 orig_blk,` 上下文中新增 `*moved_len = 0;`。
  - 在 `fs/ext4/move_extent.c` 的 `ext4_move_extents(struct file *o_filp, struct file *d_filp, __u64 orig_blk,` 上下文中将 `move_extent_per_page(o_filp, donor_inode,` 调整为 `*moved_len += move_extent_per_page(o_filp, donor_inode,`。
  - 在 `fs/ext4/move_extent.c` 的 `ext4_move_extents(struct file *o_filp, struct file *d_filp, __u64 orig_blk,` 上下文中移除 `*moved_len = o_start - orig_blk;`。

## CVE-2024-26705
- Title: parisc: BTLB: Fix crash when setting up BTLB at CPU bringup
- Affected files: arch/parisc/kernel/cache.c
- Card: cards/CVE-2024-26705.md

- 补丁主题: parisc: BTLB: Fix crash when setting up BTLB at CPU bringup
- 代码上下文: int pa_serialize_tlb_flushes __ro_after_init;
- 建议落地动作:
  - 在 `arch/parisc/kernel/cache.c` 的 `int pa_serialize_tlb_flushes __ro_after_init;` 上下文中将 `struct pdc_btlb_info btlb_info __ro_after_init;` 调整为 `struct pdc_btlb_info btlb_info;`。

## CVE-2024-26706
- Title: parisc: Fix random data corruption from exception handler
- Affected files: arch/parisc/Kconfig, arch/parisc/include/asm/assembly.h, arch/parisc/include/asm/extable.h, arch/parisc/include/asm/special_insns.h, arch/parisc/include/asm/uaccess.h, arch/parisc/kernel/unaligned.c, arch/parisc/mm/fault.c
- Card: cards/CVE-2024-26706.md

- 补丁主题: parisc: Fix random data corruption from exception handler
- 代码上下文: config PARISC, struct exception_table_entry {, unsigned long __must_check raw_copy_from_user(void *dst, const void __user *src,, static int emulate_ldh(struct pt_regs *regs, int toreg), static int emulate_ldw(struct pt_regs *regs, int toreg, int flop), static int emulate_ldd(struct pt_regs *regs, int toreg, int flop), static int emulate_sth(struct pt_regs *regs, int frreg), static int emulate_stw(struct pt_regs *regs, int frreg, int flop)
- 建议落地动作:
  - 在 `arch/parisc/Kconfig` 的 `config PARISC` 上下文中移除 `select BUILDTIME_TABLE_SORT`。
  - 在 `arch/parisc/include/asm/assembly.h` 的 `global` 上下文中新增 `or %r0,%r0,%r0 ! \`。
  - 在 `arch/parisc/include/asm/extable.h` 的 `global` 上下文中新增 `/* SPDX-License-Identifier: GPL-2.0 */`。
  - 在 `arch/parisc/include/asm/special_insns.h` 的 `global` 上下文中将 `ASM_EXCEPTIONTABLE_ENTRY(8b, 9b) \` 调整为 `ASM_EXCEPTIONTABLE_ENTRY(8b, 9b, \`。
