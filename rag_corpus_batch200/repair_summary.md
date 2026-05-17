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

## CVE-2024-26707
- Title: net: hsr: remove WARN_ONCE() in send_hsr_supervision_frame()
- Affected files: net/hsr/hsr_device.c
- Card: cards/CVE-2024-26707.md

- 补丁主题: net: hsr: remove WARN_ONCE() in send_hsr_supervision_frame()
- 代码上下文: static void send_hsr_supervision_frame(struct hsr_port *master,, static void send_prp_supervision_frame(struct hsr_port *master,
- 建议落地动作:
  - 在 `net/hsr/hsr_device.c` 的 `static void send_hsr_supervision_frame(struct hsr_port *master,` 上下文中将 `WARN_ONCE(1, "HSR: Could not send supervision frame\n");` 调整为 `netdev_warn_once(master->dev, "HSR: Could not send supervision frame\n");`。
  - 在 `net/hsr/hsr_device.c` 的 `static void send_prp_supervision_frame(struct hsr_port *master,` 上下文中将 `WARN_ONCE(1, "PRP: Could not send supervision frame\n");` 调整为 `netdev_warn_once(master->dev, "PRP: Could not send supervision frame\n");`。

## CVE-2024-26708
- Title: mptcp: really cope with fastopen race
- Affected files: net/mptcp/protocol.h
- Card: cards/CVE-2024-26708.md

- 补丁主题: mptcp: really cope with fastopen race
- 代码上下文: static inline bool subflow_simultaneous_connect(struct sock *sk)
- 建议落地动作:
  - 在 `net/mptcp/protocol.h` 的 `static inline bool subflow_simultaneous_connect(struct sock *sk)` 上下文中将 `return (1 << sk->sk_state) & (TCPF_ESTABLISHED | TCPF_FIN_WAIT1) &&` 调整为 `return (1 << sk->sk_state) &`。

## CVE-2024-26709
- Title: powerpc/iommu: Fix the missing iommu_group_put() during platform domain attach
- Affected files: arch/powerpc/kernel/iommu.c
- Card: cards/CVE-2024-26709.md

- 补丁主题: powerpc/iommu: Fix the missing iommu_group_put() during platform
- 代码上下文: spapr_tce_platform_iommu_attach_dev(struct iommu_domain *platform_domain,
- 建议落地动作:
  - 在 `arch/powerpc/kernel/iommu.c` 的 `spapr_tce_platform_iommu_attach_dev(struct iommu_domain *platform_domain,` 上下文中将 `if (!domain)` 调整为 `if (!domain) {`。

## CVE-2024-26710
- Title: powerpc/kasan: Limit KASAN thread size increase to 32KB
- Affected files: arch/powerpc/include/asm/thread_info.h
- Card: cards/CVE-2024-26710.md

- 补丁主题: powerpc/kasan: Limit KASAN thread size increase to 32KB
- 代码上下文: 未解析出 hunk 上下文
- 建议落地动作:
  - 在 `arch/powerpc/include/asm/thread_info.h` 的 `global` 上下文中将 `#ifdef CONFIG_KASAN` 调整为 `#if defined(CONFIG_KASAN) && CONFIG_THREAD_SHIFT < 15`。

## CVE-2024-26711
- Title: iio: adc: ad4130: zero-initialize clock init data
- Affected files: drivers/iio/adc/ad4130.c
- Card: cards/CVE-2024-26711.md

- 补丁主题: iio: adc: ad4130: zero-initialize clock init data
- 代码上下文: static int ad4130_setup_int_clk(struct ad4130_state *st)
- 建议落地动作:
  - 在 `drivers/iio/adc/ad4130.c` 的 `static int ad4130_setup_int_clk(struct ad4130_state *st)` 上下文中将 `struct clk_init_data init;` 调整为 `struct clk_init_data init = {};`。

## CVE-2024-26712
- Title: powerpc/kasan: Fix addr error caused by page alignment
- Affected files: arch/powerpc/mm/kasan/init_32.c
- Card: cards/CVE-2024-26712.md

- 补丁主题: powerpc/kasan: Fix addr error caused by page alignment
- 代码上下文: int __init __weak kasan_init_region(void *start, size_t size)
- 建议落地动作:
  - 在 `arch/powerpc/mm/kasan/init_32.c` 的 `int __init __weak kasan_init_region(void *start, size_t size)` 上下文中新增 `k_start = k_start & PAGE_MASK;`。

## CVE-2024-26714
- Title: interconnect: qcom: sc8180x: Mark CO0 BCM keepalive
- Affected files: drivers/interconnect/qcom/sc8180x.c
- Card: cards/CVE-2024-26714.md

- 补丁主题: interconnect: qcom: sc8180x: Mark CO0 BCM keepalive
- 代码上下文: static struct qcom_icc_bcm bcm_mm0 = {
- 建议落地动作:
  - 在 `drivers/interconnect/qcom/sc8180x.c` 的 `static struct qcom_icc_bcm bcm_mm0 = {` 上下文中新增 `.keepalive = true,`。

## CVE-2024-26715
- Title: usb: dwc3: gadget: Fix NULL pointer dereference in dwc3_gadget_suspend
- Affected files: drivers/usb/dwc3/gadget.c
- Card: cards/CVE-2024-26715.md

- 补丁主题: usb: dwc3: gadget: Fix NULL pointer dereference in
- 代码上下文: int dwc3_gadget_suspend(struct dwc3 *dwc)
- 建议落地动作:
  - 在 `drivers/usb/dwc3/gadget.c` 的 `int dwc3_gadget_suspend(struct dwc3 *dwc)` 上下文中调整 `dwc3_disconnect_gadget()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/usb/dwc3/gadget.c` 的 `int dwc3_gadget_suspend(struct dwc3 *dwc)` 上下文中将 `if (!dwc->gadget_driver)` 调整为 `if (dwc->gadget_driver)`。

## CVE-2024-26716
- Title: usb: core: Prevent null pointer dereference in update_port_device_state
- Affected files: drivers/usb/core/hub.c
- Card: cards/CVE-2024-26716.md

- 补丁主题: usb: core: Prevent null pointer dereference in
- 代码上下文: static void update_port_device_state(struct usb_device *udev)
- 建议落地动作:
  - 在 `drivers/usb/core/hub.c` 的 `static void update_port_device_state(struct usb_device *udev)` 上下文中调整 `WRITE_ONCE()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/usb/core/hub.c` 的 `static void update_port_device_state(struct usb_device *udev)` 上下文中将 `port_dev = hub->ports[udev->portnum - 1];` 调整为 `* The Link Layer Validation System Driver (lvstest)`。

## CVE-2024-26717
- Title: HID: i2c-hid-of: fix NULL-deref on failed power up
- Affected files: drivers/hid/i2c-hid/i2c-hid-of.c
- Card: cards/CVE-2024-26717.md

- 补丁主题: HID: i2c-hid-of: fix NULL-deref on failed power up
- 代码上下文: static int i2c_hid_of_probe(struct i2c_client *client)
- 建议落地动作:
  - 在 `drivers/hid/i2c-hid/i2c-hid-of.c` 的 `static int i2c_hid_of_probe(struct i2c_client *client)` 上下文中新增 `ihid_of->client = client;`。

## CVE-2024-26718
- Title: dm-crypt, dm-verity: disable tasklets
- Affected files: drivers/md/dm-crypt.c, drivers/md/dm-verity-target.c, drivers/md/dm-verity.h
- Card: cards/CVE-2024-26718.md

- 补丁主题: dm-crypt, dm-verity: disable tasklets
- 代码上下文: struct dm_crypt_io {, static void crypt_io_init(struct dm_crypt_io *io, struct crypt_config *cc,, static void crypt_inc_pending(struct dm_crypt_io *io), static void crypt_dec_pending(struct dm_crypt_io *io), static void kcryptd_crypt(struct work_struct *work), static void kcryptd_queue_crypt(struct dm_crypt_io *io), static void verity_work(struct work_struct *w), static void verity_end_io(struct bio *bio)
- 建议落地动作:
  - 在 `drivers/md/dm-crypt.c` 的 `struct dm_crypt_io {` 上下文中移除 `bool in_tasklet:1;`。
  - 在 `drivers/md/dm-crypt.c` 的 `static void crypt_io_init(struct dm_crypt_io *io, struct crypt_config *cc,` 上下文中移除 `io->in_tasklet = false;`。
  - 在 `drivers/md/dm-crypt.c` 的 `static void crypt_inc_pending(struct dm_crypt_io *io)` 上下文中移除 `static void kcryptd_io_bio_endio(struct work_struct *work)`。
  - 在 `drivers/md/dm-crypt.c` 的 `static void crypt_dec_pending(struct dm_crypt_io *io)` 上下文中移除 `* If we are running this function from our tasklet,`。

## CVE-2024-26719
- Title: nouveau: offload fence uevents work to workqueue
- Affected files: drivers/gpu/drm/nouveau/nouveau_fence.c, drivers/gpu/drm/nouveau/nouveau_fence.h
- Card: cards/CVE-2024-26719.md

- 补丁主题: nouveau: offload fence uevents work to workqueue
- 代码上下文: nouveau_fence_context_kill(struct nouveau_fence_chan *fctx, int error), nouveau_fence_update(struct nouveau_channel *chan, struct nouveau_fence_chan *fc, nouveau_fence_wait_uevent_handler(struct nvif_event *event, void *repv, u32 repc, nouveau_fence_context_new(struct nouveau_channel *chan, struct nouveau_fence_cha, struct nouveau_fence_chan {
- 建议落地动作:
  - 在 `drivers/gpu/drm/nouveau/nouveau_fence.c` 中调整 `nouveau_fence_wait_uevent_handler()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/nouveau/nouveau_fence.c` 的 `nouveau_fence_context_kill(struct nouveau_fence_chan *fctx, int error)` 上下文中新增 `cancel_work_sync(&fctx->uevent_work);`。
  - 在 `drivers/gpu/drm/nouveau/nouveau_fence.c` 的 `nouveau_fence_update(struct nouveau_channel *chan, struct nouveau_fence_chan *fc` 上下文中将 `static int` 调整为 `static void`。
  - 在 `drivers/gpu/drm/nouveau/nouveau_fence.c` 的 `nouveau_fence_wait_uevent_handler(struct nvif_event *event, void *repv, u32 repc` 上下文中将 `ret = NVIF_EVENT_DROP;` 调整为 `drop = 1;`。

## CVE-2024-26721
- Title: drm/i915/dsc: Fix the macro that calculates DSCC_/DSCA_ PPS reg address
- Affected files: drivers/gpu/drm/i915/display/intel_vdsc_regs.h
- Card: cards/CVE-2024-26721.md

- 补丁主题: drm/i915/dsc: Fix the macro that calculates DSCC_/DSCA_ PPS reg
- 代码上下文: 未解析出 hunk 上下文
- 建议落地动作:
  - 在 `drivers/gpu/drm/i915/display/intel_vdsc_regs.h` 的 `global` 上下文中将 `#define DSCA_PPS(pps) _MMIO(_DSCA_PPS_0 + (pps) * 4)` 调整为 `#define DSCA_PPS(pps) _MMIO(_DSCA_PPS_0 + ((pps) < 12 ? (pps) : (pps) + 12) * 4)`。

## CVE-2024-26722
- Title: ASoC: rt5645: Fix deadlock in rt5645_jack_detect_work()
- Affected files: sound/soc/codecs/rt5645.c
- Card: cards/CVE-2024-26722.md

- 补丁主题: ASoC: rt5645: Fix deadlock in rt5645_jack_detect_work()
- 代码上下文: static void rt5645_jack_detect_work(struct work_struct *work)
- 建议落地动作:
  - 在 `sound/soc/codecs/rt5645.c` 的 `static void rt5645_jack_detect_work(struct work_struct *work)` 上下文中新增 `mutex_unlock(&rt5645->jd_mutex);`。

## CVE-2024-26723
- Title: lan966x: Fix crash when adding interface under a lag
- Affected files: drivers/net/ethernet/microchip/lan966x/lan966x_lag.c
- Card: cards/CVE-2024-26723.md

- 补丁主题: lan966x: Fix crash when adding interface under a lag
- 代码上下文: static void lan966x_lag_set_aggr_pgids(struct lan966x *lan966x)
- 建议落地动作:
  - 在 `drivers/net/ethernet/microchip/lan966x/lan966x_lag.c` 的 `static void lan966x_lag_set_aggr_pgids(struct lan966x *lan966x)` 上下文中将 `struct net_device *bond = lan966x->ports[lag]->bond;` 调整为 `struct lan966x_port *port = lan966x->ports[lag];`。

## CVE-2024-26724
- Title: net/mlx5: DPLL, Fix possible use after free after delayed work timer triggers
- Affected files: drivers/net/ethernet/mellanox/mlx5/core/dpll.c
- Card: cards/CVE-2024-26724.md

- 补丁主题: net/mlx5: DPLL, Fix possible use after free after delayed work timer
- 代码上下文: static void mlx5_dpll_remove(struct auxiliary_device *adev)
- 建议落地动作:
  - 在 `drivers/net/ethernet/mellanox/mlx5/core/dpll.c` 的 `static void mlx5_dpll_remove(struct auxiliary_device *adev)` 上下文中将 `cancel_delayed_work(&mdpll->work);` 调整为 `cancel_delayed_work_sync(&mdpll->work);`。

## CVE-2024-26725
- Title: dpll: fix possible deadlock during netlink dump operation
- Affected files: Documentation/netlink/specs/dpll.yaml, drivers/dpll/dpll_netlink.c, drivers/dpll/dpll_nl.c, drivers/dpll/dpll_nl.h
- Card: cards/CVE-2024-26725.md

- 补丁主题: dpll: fix possible deadlock during netlink dump operation
- 代码上下文: operations:, int dpll_nl_pin_get_dumpit(struct sk_buff *skb, struct netlink_callback *cb), int dpll_nl_device_get_dumpit(struct sk_buff *skb, struct netlink_callback *cb), dpll_unlock_doit(const struct genl_split_ops *ops, struct sk_buff *skb,, static const struct genl_split_ops dpll_nl_ops[] = {, dpll_post_doit(const struct genl_split_ops *ops, struct sk_buff *skb,
- 建议落地动作:
  - 在 `Documentation/netlink/specs/dpll.yaml` 的 `operations:` 上下文中移除 `pre: dpll-lock-dumpit`。
  - 在 `drivers/dpll/dpll_netlink.c` 的 `int dpll_nl_pin_get_dumpit(struct sk_buff *skb, struct netlink_callback *cb)` 上下文中新增 `mutex_lock(&dpll_lock);`。
  - 在 `drivers/dpll/dpll_netlink.c` 的 `int dpll_nl_pin_get_dumpit(struct sk_buff *skb, struct netlink_callback *cb)` 上下文中新增 `mutex_unlock(&dpll_lock);`。

## CVE-2024-26726
- Title: btrfs: don't drop extent_map for free space inode on write error
- Affected files: fs/btrfs/inode.c
- Card: cards/CVE-2024-26726.md

- 补丁主题: btrfs: don't drop extent_map for free space inode on write error
- 代码上下文: out:
- 建议落地动作:
  - 在 `fs/btrfs/inode.c` 的 `out:` 上下文中将 `/* Drop extent maps for the part of the extent we didn't write. */` 调整为 `* Drop extent maps for the part of the extent we didn't write.`。

## CVE-2024-26727
- Title: btrfs: do not ASSERT() if the newly created subvolume already got read
- Affected files: fs/btrfs/disk-io.c
- Card: cards/CVE-2024-26727.md

- 补丁主题: btrfs: do not ASSERT() if the newly created subvolume already got
- 代码上下文: static struct btrfs_root *btrfs_get_root_ref(struct btrfs_fs_info *fs_info,
- 建议落地动作:
  - 在 `fs/btrfs/disk-io.c` 的 `static struct btrfs_root *btrfs_get_root_ref(struct btrfs_fs_info *fs_info,` 上下文中将 `/* Shouldn't get preallocated anon_dev for cached roots */` 调整为 `* Some other caller may have read out the newly inserted`。

## CVE-2024-26728
- Title: drm/amd/display: fix null-pointer dereference on edid reading
- Affected files: drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c
- Card: cards/CVE-2024-26728.md

- 补丁主题: drm/amd/display: fix null-pointer dereference on edid reading
- 代码上下文: amdgpu_dm_connector_late_register(struct drm_connector *connector), static void amdgpu_dm_connector_funcs_force(struct drm_connector *connector), static int get_modes(struct drm_connector *connector), static void create_eml_sink(struct amdgpu_dm_connector *aconnector)
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c` 的 `amdgpu_dm_connector_late_register(struct drm_connector *connector)` 上下文中将 `struct amdgpu_connector *amdgpu_connector = to_amdgpu_connector(connector);` 调整为 `struct i2c_adapter *ddc;`。
  - 在 `drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c` 的 `static void amdgpu_dm_connector_funcs_force(struct drm_connector *connector)` 上下文中将 `edid = drm_get_edid(connector, &amdgpu_connector->ddc_bus->aux.ddc);` 调整为 `edid = drm_get_edid(connector, ddc);`。
  - 在 `drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c` 的 `static int get_modes(struct drm_connector *connector)` 上下文中将 `struct amdgpu_connector *amdgpu_connector = to_amdgpu_connector(&aconnector->base);` 调整为 `struct dc_link *dc_link = aconnector->dc_link;`。
  - 在 `drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c` 的 `static void create_eml_sink(struct amdgpu_dm_connector *aconnector)` 上下文中将 `edid = drm_get_edid(connector, &amdgpu_connector->ddc_bus->aux.ddc);` 调整为 `edid = drm_get_edid(connector, ddc);`。

## CVE-2024-26729
- Title: drm/amd/display: Fix potential null pointer dereference in dc_dmub_srv
- Affected files: drivers/gpu/drm/amd/display/dc/dc_dmub_srv.c
- Card: cards/CVE-2024-26729.md

- 补丁主题: drm/amd/display: Fix potential null pointer dereference in
- 代码上下文: bool dc_dmub_srv_cmd_list_queue_execute(struct dc_dmub_srv *dc_dmub_srv,, void dc_dmub_srv_subvp_save_surf_addr(const struct dc_dmub_srv *dc_dmub_srv, con, bool dc_dmub_srv_is_hw_pwr_up(struct dc_dmub_srv *dc_dmub_srv, bool wait)
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/dc_dmub_srv.c` 的 `bool dc_dmub_srv_cmd_list_queue_execute(struct dc_dmub_srv *dc_dmub_srv,` 上下文中将 `struct dc_context *dc_ctx = dc_dmub_srv->ctx;` 调整为 `struct dc_context *dc_ctx;`。
  - 在 `drivers/gpu/drm/amd/display/dc/dc_dmub_srv.c` 的 `bool dc_dmub_srv_cmd_list_queue_execute(struct dc_dmub_srv *dc_dmub_srv,` 上下文中新增 `dc_ctx = dc_dmub_srv->ctx;`。
  - 在 `drivers/gpu/drm/amd/display/dc/dc_dmub_srv.c` 的 `void dc_dmub_srv_subvp_save_surf_addr(const struct dc_dmub_srv *dc_dmub_srv, con` 上下文中将 `struct dc_context *dc_ctx = dc_dmub_srv->ctx;` 调整为 `struct dc_context *dc_ctx;`。
  - 在 `drivers/gpu/drm/amd/display/dc/dc_dmub_srv.c` 的 `bool dc_dmub_srv_is_hw_pwr_up(struct dc_dmub_srv *dc_dmub_srv, bool wait)` 上下文中新增 `dc_ctx = dc_dmub_srv->ctx;`。

## CVE-2024-26730
- Title: hwmon: (nct6775) Fix access to temperature configuration registers
- Affected files: drivers/hwmon/nct6775-core.c
- Card: cards/CVE-2024-26730.md

- 补丁主题: hwmon: (nct6775) Fix access to temperature configuration registers
- 代码上下文: int nct6775_probe(struct device *dev, struct nct6775_data *data,
- 建议落地动作:
  - 在 `drivers/hwmon/nct6775-core.c` 的 `int nct6775_probe(struct device *dev, struct nct6775_data *data,` 上下文中新增 `int num_reg_temp_config;`。
  - 在 `drivers/hwmon/nct6775-core.c` 的 `int nct6775_probe(struct device *dev, struct nct6775_data *data,` 上下文中新增 `num_reg_temp_config = ARRAY_SIZE(NCT6106_REG_TEMP_CONFIG);`。
  - 在 `drivers/hwmon/nct6775-core.c` 的 `int nct6775_probe(struct device *dev, struct nct6775_data *data,` 上下文中新增 `num_reg_temp_config = ARRAY_SIZE(NCT6775_REG_TEMP_CONFIG);`。

## CVE-2024-26731
- Title: bpf, sockmap: Fix NULL pointer dereference in sk_psock_verdict_data_ready()
- Affected files: net/core/skmsg.c
- Card: cards/CVE-2024-26731.md

- 补丁主题: bpf, sockmap: Fix NULL pointer dereference in
- 代码上下文: static void sk_psock_verdict_data_ready(struct sock *sk)
- 建议落地动作:
  - 在 `net/core/skmsg.c` 的 `static void sk_psock_verdict_data_ready(struct sock *sk)` 上下文中将 `if (psock)` 调整为 `if (psock) {`。

## CVE-2024-26732
- Title: net: implement lockless setsockopt(SO_PEEK_OFF)
- Affected files: net/core/sock.c, net/ipv4/udp.c, net/unix/af_unix.c
- Card: cards/CVE-2024-26732.md

- 补丁主题: net: implement lockless setsockopt(SO_PEEK_OFF)
- 代码上下文: int sk_setsockopt(struct sock *sk, int level, int optname,, set_sndbuf:, int udp_init_sock(struct sock *sk), static int unix_seqpacket_sendmsg(struct socket *, struct msghdr *, size_t);, static const struct proto_ops unix_stream_ops = {, static const struct proto_ops unix_dgram_ops = {, static const struct proto_ops unix_seqpacket_ops = {
- 建议落地动作:
  - 在该补丁中调整 `int()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/core/sock.c` 的 `int sk_setsockopt(struct sock *sk, int level, int optname,` 上下文中新增 `case SO_PEEK_OFF:`。
  - 在 `net/core/sock.c` 的 `set_sndbuf:` 上下文中移除 `case SO_PEEK_OFF:`。
  - 在 `net/ipv4/udp.c` 的 `int udp_init_sock(struct sock *sk)` 上下文中将 `if (unlikely(READ_ONCE(sk->sk_peek_off) >= 0)) {` 调整为 `sk_peek_offset_bwd(sk, len);`。

## CVE-2024-26733
- Title: arp: Prevent overflow in arp_req_get().
- Affected files: net/ipv4/arp.c
- Card: cards/CVE-2024-26733.md

- 补丁主题: arp: Prevent overflow in arp_req_get().
- 代码上下文: static int arp_req_get(struct arpreq *r, struct net_device *dev)
- 建议落地动作:
  - 在 `net/ipv4/arp.c` 的 `static int arp_req_get(struct arpreq *r, struct net_device *dev)` 上下文中将 `memcpy(r->arp_ha.sa_data, neigh->ha, dev->addr_len);` 调整为 `memcpy(r->arp_ha.sa_data, neigh->ha,`。

## CVE-2024-26734
- Title: devlink: fix possible use-after-free and memory leaks in devlink_init()
- Affected files: net/devlink/core.c
- Card: cards/CVE-2024-26734.md

- 补丁主题: devlink: fix possible use-after-free and memory leaks in
- 代码上下文: static int __init devlink_init(void)
- 建议落地动作:
  - 在 `net/devlink/core.c` 的 `static int __init devlink_init(void)` 上下文中调整 `genl_register_family()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/devlink/core.c` 的 `static int __init devlink_init(void)` 上下文中调整 `genl_register_family()` 的调用位置，使其与新的初始化顺序保持一致。

## CVE-2024-26735
- Title: ipv6: sr: fix possible use-after-free and null-ptr-deref
- Affected files: net/ipv6/seg6.c
- Card: cards/CVE-2024-26735.md

- 补丁主题: ipv6: sr: fix possible use-after-free and null-ptr-deref
- 代码上下文: int __init seg6_init(void), out_unregister_iptun:
- 建议落地动作:
  - 在 `net/ipv6/seg6.c` 中调整 `genl_register_family()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/ipv6/seg6.c` 的 `int __init seg6_init(void)` 上下文中将 `err = genl_register_family(&seg6_genl_family);` 调整为 `err = register_pernet_subsys(&ip6_segments_ops);`。
  - 在 `net/ipv6/seg6.c` 的 `out_unregister_iptun:` 上下文中将 `out_unregister_pernet:` 调整为 `#endif`。

## CVE-2024-26736
- Title: afs: Increase buffer size in afs_update_volume_status()
- Affected files: fs/afs/volume.c
- Card: cards/CVE-2024-26736.md

- 补丁主题: afs: Increase buffer size in afs_update_volume_status()
- 代码上下文: static int afs_update_volume_status(struct afs_volume *volume, struct key *key)
- 建议落地动作:
  - 在 `fs/afs/volume.c` 的 `static int afs_update_volume_status(struct afs_volume *volume, struct key *key)` 上下文中将 `char idbuf[16];` 调整为 `char idbuf[24];`。
  - 在 `fs/afs/volume.c` 的 `static int afs_update_volume_status(struct afs_volume *volume, struct key *key)` 上下文中将 `idsz = sprintf(idbuf, "%llu", volume->vid);` 调整为 `idsz = snprintf(idbuf, sizeof(idbuf), "%llu", volume->vid);`。

## CVE-2024-26737
- Title: bpf: Fix racing between bpf_timer_cancel_and_free and bpf_timer_cancel
- Affected files: kernel/bpf/helpers.c
- Card: cards/CVE-2024-26737.md

- 补丁主题: bpf: Fix racing between bpf_timer_cancel_and_free and
- 代码上下文: struct bpf_hrtimer {, BPF_CALL_1(bpf_timer_cancel, struct bpf_timer_kern *, timer), out:
- 建议落地动作:
  - 在 `kernel/bpf/helpers.c` 的 `struct bpf_hrtimer {` 上下文中新增 `struct rcu_head rcu;`。
  - 在 `kernel/bpf/helpers.c` 的 `BPF_CALL_1(bpf_timer_cancel, struct bpf_timer_kern *, timer)` 上下文中新增 `rcu_read_lock();`。
  - 在 `kernel/bpf/helpers.c` 的 `out:` 上下文中新增 `rcu_read_unlock();`。
  - 在 `kernel/bpf/helpers.c` 的 `out:` 上下文中将 `kfree(t);` 调整为 `kfree_rcu(t, rcu);`。

## CVE-2024-26738
- Title: powerpc/pseries/iommu: DLPAR add doesn't completely initialize pci_controller
- Affected files: arch/powerpc/include/asm/ppc-pci.h, arch/powerpc/kernel/iommu.c, arch/powerpc/platforms/pseries/pci_dlpar.c
- Card: cards/CVE-2024-26738.md

- 补丁主题: powerpc/pseries/iommu: DLPAR add doesn't completely initialize
- 代码上下文: void *pci_traverse_device_nodes(struct device_node *start,, static struct iommu_device *spapr_tce_iommu_probe_device(struct device *dev), static const struct attribute_group *spapr_tce_iommu_groups[] = {, static int __init spapr_tce_setup_phb_iommus_initcall(void), struct pci_controller *init_phb_dynamic(struct device_node *dn), int remove_phb_dynamic(struct pci_controller *phb)
- 建议落地动作:
  - 在 `arch/powerpc/include/asm/ppc-pci.h` 的 `void *pci_traverse_device_nodes(struct device_node *start,` 上下文中新增 `#if defined(CONFIG_IOMMU_API) && (defined(CONFIG_PPC_PSERIES) || \`。
  - 在 `arch/powerpc/kernel/iommu.c` 的 `static struct iommu_device *spapr_tce_iommu_probe_device(struct device *dev)` 上下文中将 `return ERR_PTR(-EPERM);` 调整为 `return ERR_PTR(-ENODEV);`。
  - 在 `arch/powerpc/kernel/iommu.c` 的 `static const struct attribute_group *spapr_tce_iommu_groups[] = {` 上下文中新增 `void ppc_iommu_register_device(struct pci_controller *phb)`。
  - 在 `arch/powerpc/kernel/iommu.c` 的 `static int __init spapr_tce_setup_phb_iommus_initcall(void)` 上下文中将 `iommu_device_sysfs_add(&hose->iommu, hose->parent,` 调整为 `ppc_iommu_register_device(hose);`。

## CVE-2024-26739
- Title: net/sched: act_mirred: don't override retval if we already lost the skb
- Affected files: net/sched/act_mirred.c
- Card: cards/CVE-2024-26739.md

- 补丁主题: net/sched: act_mirred: don't override retval if we already lost the
- 代码上下文: static int tcf_mirred_act(struct sk_buff *skb, const struct tc_action *a,
- 建议落地动作:
  - 在 `net/sched/act_mirred.c` 的 `static int tcf_mirred_act(struct sk_buff *skb, const struct tc_action *a,` 上下文中调整 `tcf_mirred_is_act_redirect()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/sched/act_mirred.c` 的 `static int tcf_mirred_act(struct sk_buff *skb, const struct tc_action *a,` 上下文中将 `goto out;` 调整为 `is_redirect = tcf_mirred_is_act_redirect(m_eaction);`。
  - 在 `net/sched/act_mirred.c` 的 `static int tcf_mirred_act(struct sk_buff *skb, const struct tc_action *a,` 上下文中将 `if (err) {` 调整为 `if (err)`。

## CVE-2024-26740
- Title: net/sched: act_mirred: use the backlog for mirred ingress
- Affected files: net/sched/act_mirred.c, tools/testing/selftests/net/forwarding/tc_actions.sh
- Card: cards/CVE-2024-26740.md

- 补丁主题: net/sched: act_mirred: use the backlog for mirred ingress
- 代码上下文: release_idr:, static int tcf_mirred_to_dev(struct sk_buff *skb, struct tcf_mirred *m,, mirred_egress_to_ingress_tcp_test()
- 建议落地动作:
  - 在 `net/sched/act_mirred.c` 的 `release_idr:` 上下文中将 `static bool is_mirred_nested(void)` 调整为 `static int`。
  - 在 `net/sched/act_mirred.c` 的 `static int tcf_mirred_to_dev(struct sk_buff *skb, struct tcf_mirred *m,` 上下文中将 `err = tcf_mirred_forward(want_ingress, skb_to_send);` 调整为 `err = tcf_mirred_forward(at_ingress, want_ingress, skb_to_send);`。
  - 在 `tools/testing/selftests/net/forwarding/tc_actions.sh` 的 `mirred_egress_to_ingress_tcp_test()` 上下文中移除 `local overlimits=$(tc_rule_stats_get ${h1} 101 egress .overlimits)`。

## CVE-2024-26741
- Title: dccp/tcp: Unhash sk from ehash for tb2 alloc failure after check_estalblished().
- Affected files: net/ipv4/inet_hashtables.c
- Card: cards/CVE-2024-26741.md

- 补丁主题: dccp/tcp: Unhash sk from ehash for tb2 alloc failure after
- 代码上下文: ok:
- 建议落地动作:
  - 在 `net/ipv4/inet_hashtables.c` 的 `ok:` 上下文中将 `spin_unlock_bh(&head->lock);` 调整为 `if (sk_hashed(sk)) {`。

## CVE-2024-26742
- Title: scsi: smartpqi: Fix disable_managed_interrupts
- Affected files: drivers/scsi/smartpqi/smartpqi_init.c
- Card: cards/CVE-2024-26742.md

- 补丁主题: scsi: smartpqi: Fix disable_managed_interrupts
- 代码上下文: static void pqi_map_queues(struct Scsi_Host *shost)
- 建议落地动作:
  - 在 `drivers/scsi/smartpqi/smartpqi_init.c` 的 `static void pqi_map_queues(struct Scsi_Host *shost)` 上下文中将 `blk_mq_pci_map_queues(&shost->tag_set.map[HCTX_TYPE_DEFAULT],` 调整为 `if (!ctrl_info->disable_managed_interrupts)`。

## CVE-2024-26743
- Title: RDMA/qedr: Fix qedr_create_user_qp error flow
- Affected files: drivers/infiniband/hw/qedr/verbs.c
- Card: cards/CVE-2024-26743.md

- 补丁主题: RDMA/qedr: Fix qedr_create_user_qp error flow
- 代码上下文: static int qedr_create_user_qp(struct qedr_dev *dev,
- 建议落地动作:
  - 在 `drivers/infiniband/hw/qedr/verbs.c` 的 `static int qedr_create_user_qp(struct qedr_dev *dev,` 上下文中将 `if (rc)` 调整为 `if (rc) {`。

## CVE-2024-26744
- Title: RDMA/srpt: Support specifying the srpt_service_guid parameter
- Affected files: drivers/infiniband/ulp/srpt/ib_srpt.c
- Card: cards/CVE-2024-26744.md

- 补丁主题: RDMA/srpt: Support specifying the srpt_service_guid parameter
- 代码上下文: module_param(srpt_srq_size, int, 0444);
- 建议落地动作:
  - 在 `drivers/infiniband/ulp/srpt/ib_srpt.c` 的 `module_param(srpt_srq_size, int, 0444);` 上下文中将 `module_param_call(srpt_service_guid, NULL, srpt_get_u64_x, &srpt_service_guid,` 调整为 `static int srpt_set_u64_x(const char *buffer, const struct kernel_param *kp)`。

## CVE-2024-26745
- Title: powerpc/pseries/iommu: IOMMU table is not initialized for kdump over SR-IOV
- Affected files: arch/powerpc/platforms/pseries/iommu.c
- Card: cards/CVE-2024-26745.md

- 补丁主题: powerpc/pseries/iommu: IOMMU table is not initialized for kdump over
- 代码上下文: static void iommu_table_setparms(struct pci_controller *phb,, struct iommu_table_ops iommu_table_lpar_multi_ops = {, static void pci_dma_bus_setup_pSeriesLP(struct pci_bus *bus), static void find_existing_ddw_windows_named(const char *name), static void pci_dma_dev_setup_pSeriesLP(struct pci_dev *dev)
- 建议落地动作:
  - 在 `arch/powerpc/platforms/pseries/iommu.c` 中调整 `iommu_init_table()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `arch/powerpc/platforms/pseries/iommu.c` 的 `static void iommu_table_setparms(struct pci_controller *phb,` 上下文中移除 `* iommu_table_setparms_lpar`。
  - 在 `arch/powerpc/platforms/pseries/iommu.c` 的 `struct iommu_table_ops iommu_table_lpar_multi_ops = {` 上下文中将 `const __be32 **dma_window)` 调整为 `struct dynamic_dma_window_prop *prop)`。
  - 在 `arch/powerpc/platforms/pseries/iommu.c` 的 `static void pci_dma_bus_setup_pSeriesLP(struct pci_bus *bus)` 上下文中将 `const __be32 *dma_window = NULL;` 调整为 `struct dynamic_dma_window_prop prop;`。

## CVE-2024-26746
- Title: dmaengine: idxd: Ensure safe user copy of completion record
- Affected files: drivers/dma/idxd/init.c
- Card: cards/CVE-2024-26746.md

- 补丁主题: dmaengine: idxd: Ensure safe user copy of completion record
- 代码上下文: static void idxd_cleanup_internals(struct idxd_device *idxd), static int idxd_init_evl(struct idxd_device *idxd)
- 建议落地动作:
  - 在 `drivers/dma/idxd/init.c` 的 `static void idxd_cleanup_internals(struct idxd_device *idxd)` 上下文中新增 `unsigned int evl_cache_size;`。
  - 在 `drivers/dma/idxd/init.c` 的 `static int idxd_init_evl(struct idxd_device *idxd)` 上下文中将 `idxd->evl_cache = kmem_cache_create(dev_name(idxd_confdev(idxd)),` 调整为 `idxd_name = dev_name(idxd_confdev(idxd));`。

## CVE-2024-26747
- Title: usb: roles: fix NULL pointer issue when put module's reference
- Affected files: drivers/usb/roles/class.c
- Card: cards/CVE-2024-26747.md

- 补丁主题: usb: roles: fix NULL pointer issue when put module's reference
- 代码上下文: static struct class *role_class;, struct usb_role_switch *usb_role_switch_get(struct device *dev), struct usb_role_switch *fwnode_usb_role_switch_get(struct fwnode_handle *fwnode), EXPORT_SYMBOL_GPL(fwnode_usb_role_switch_get);, struct usb_role_switch *, usb_role_switch_register(struct device *parent,
- 建议落地动作:
  - 在 `drivers/usb/roles/class.c` 的 `static struct class *role_class;` 上下文中新增 `struct module *module; /* the module this device depends on */`。
  - 在 `drivers/usb/roles/class.c` 的 `struct usb_role_switch *usb_role_switch_get(struct device *dev)` 上下文中将 `WARN_ON(!try_module_get(sw->dev.parent->driver->owner));` 调整为 `WARN_ON(!try_module_get(sw->module));`。
  - 在 `drivers/usb/roles/class.c` 的 `struct usb_role_switch *fwnode_usb_role_switch_get(struct fwnode_handle *fwnode)` 上下文中将 `WARN_ON(!try_module_get(sw->dev.parent->driver->owner));` 调整为 `WARN_ON(!try_module_get(sw->module));`。
  - 在 `drivers/usb/roles/class.c` 的 `EXPORT_SYMBOL_GPL(fwnode_usb_role_switch_get);` 上下文中将 `module_put(sw->dev.parent->driver->owner);` 调整为 `module_put(sw->module);`。

## CVE-2024-26748
- Title: usb: cdns3: fix memory double free when handle zero packet
- Affected files: drivers/usb/cdns3/gadget.c
- Card: cards/CVE-2024-26748.md

- 补丁主题: usb: cdns3: fix memory double free when handle zero packet
- 代码上下文: void cdns3_gadget_giveback(struct cdns3_endpoint *priv_ep,
- 建议落地动作:
  - 在 `drivers/usb/cdns3/gadget.c` 的 `void cdns3_gadget_giveback(struct cdns3_endpoint *priv_ep,` 上下文中将 `if (request->complete) {` 调整为 `* zlp request is appended by driver, needn't call usb_gadget_giveback_request() to notify`。

## CVE-2024-26749
- Title: usb: cdns3: fixed memory use after free at cdns3_gadget_ep_disable()
- Affected files: drivers/usb/cdns3/cdns3-gadget.c
- Card: cards/CVE-2024-26749.md

- 补丁主题: usb: cdns3: fixed memory use after free at cdns3_gadget_ep_disable()
- 代码上下文: static int cdns3_gadget_ep_disable(struct usb_ep *ep)
- 建议落地动作:
  - 在 `drivers/usb/cdns3/cdns3-gadget.c` 的 `static int cdns3_gadget_ep_disable(struct usb_ep *ep)` 上下文中调整 `list_del_init()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/usb/cdns3/cdns3-gadget.c` 的 `static int cdns3_gadget_ep_disable(struct usb_ep *ep)` 上下文中调整 `list_del_init()` 的调用位置，使其与新的初始化顺序保持一致。

## CVE-2024-26750
- Title: af_unix: Drop oob_skb ref before purging queue in GC.
- Affected files: net/unix/garbage.c
- Card: cards/CVE-2024-26750.md

- 补丁主题: af_unix: Drop oob_skb ref before purging queue in GC.
- 代码上下文: void unix_gc(void)
- 建议落地动作:
  - 在 `net/unix/garbage.c` 的 `void unix_gc(void)` 上下文中调整 `IS_ENABLED()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/unix/garbage.c` 的 `void unix_gc(void)` 上下文中将 `list_for_each_entry(u, &gc_candidates, link)` 调整为 `list_for_each_entry(u, &gc_candidates, link) {`。
  - 在 `net/unix/garbage.c` 的 `void unix_gc(void)` 上下文中移除 `#if IS_ENABLED(CONFIG_AF_UNIX_OOB)`。

## CVE-2024-26751
- Title: ARM: ep93xx: Add terminator to gpiod_lookup_table
- Affected files: arch/arm/mach-ep93xx/core.c
- Card: cards/CVE-2024-26751.md

- 补丁主题: ARM: ep93xx: Add terminator to gpiod_lookup_table
- 代码上下文: static struct gpiod_lookup_table ep93xx_i2c_gpiod_table = {
- 建议落地动作: 当前仅拿到原始补丁，需人工结合 patch hunk 做更细粒度摘要。

## CVE-2024-26752
- Title: l2tp: pass correct message length to ip6_append_data
- Affected files: net/l2tp/l2tp_ip6.c
- Card: cards/CVE-2024-26752.md

- 补丁主题: l2tp: pass correct message length to ip6_append_data
- 代码上下文: static int l2tp_ip6_sendmsg(struct sock *sk, struct msghdr *msg, size_t len)
- 建议落地动作:
  - 在 `net/l2tp/l2tp_ip6.c` 的 `static int l2tp_ip6_sendmsg(struct sock *sk, struct msghdr *msg, size_t len)` 上下文中将 `ulen = len + skb_queue_empty(&sk->sk_write_queue) ? transhdrlen : 0;` 调整为 `ulen = len + (skb_queue_empty(&sk->sk_write_queue) ? transhdrlen : 0);`。

## CVE-2024-26753
- Title: crypto: virtio/akcipher - Fix stack overflow on memcpy
- Affected files: drivers/crypto/virtio/virtio_crypto_akcipher_algs.c
- Card: cards/CVE-2024-26753.md

- 补丁主题: crypto: virtio/akcipher - Fix stack overflow on memcpy
- 代码上下文: static void virtio_crypto_dataq_akcipher_callback(struct virtio_crypto_request *, static int virtio_crypto_alg_akcipher_init_session(struct virtio_crypto_akcipher
- 建议落地动作:
  - 在 `drivers/crypto/virtio/virtio_crypto_akcipher_algs.c` 的 `static void virtio_crypto_dataq_akcipher_callback(struct virtio_crypto_request *` 上下文中将 `struct virtio_crypto_ctrl_header *header, void *para,` 调整为 `struct virtio_crypto_ctrl_header *header,`。
  - 在 `drivers/crypto/virtio/virtio_crypto_akcipher_algs.c` 的 `static int virtio_crypto_alg_akcipher_init_session(struct virtio_crypto_akcipher` 上下文中将 `memcpy(&ctrl->u, para, sizeof(ctrl->u));` 调整为 `memcpy(&ctrl->u.akcipher_create_session.para, para, sizeof(*para));`。

## CVE-2024-26754
- Title: gtp: fix use-after-free and null-ptr-deref in gtp_genl_dump_pdp()
- Affected files: drivers/net/gtp.c
- Card: cards/CVE-2024-26754.md

- 补丁主题: gtp: fix use-after-free and null-ptr-deref in gtp_genl_dump_pdp()
- 代码上下文: static int __init gtp_init(void)
- 建议落地动作:
  - 在 `drivers/net/gtp.c` 的 `static int __init gtp_init(void)` 上下文中调整 `genl_register_family()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/net/gtp.c` 的 `static int __init gtp_init(void)` 上下文中将 `err = genl_register_family(&gtp_genl_family);` 调整为 `err = register_pernet_subsys(&gtp_net_ops);`。

## CVE-2024-26755
- Title: md: Don't suspend the array for interrupted reshape
- Affected files: drivers/md/md.c
- Card: cards/CVE-2024-26755.md

- 补丁主题: md: Don't suspend the array for interrupted reshape
- 代码上下文: static void md_start_sync(struct work_struct *ws)
- 建议落地动作:
  - 在 `drivers/md/md.c` 的 `static void md_start_sync(struct work_struct *ws)` 上下文中调整 `mddev_lock_nointr()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/md/md.c` 的 `static void md_start_sync(struct work_struct *ws)` 上下文中将 `if (md_spares_need_change(mddev))` 调整为 `* If reshape is still in progress, spares won't be added or removed`。

## CVE-2024-26756
- Title: md: Don't register sync_thread for reshape directly
- Affected files: drivers/md/md.c, drivers/md/raid10.c, drivers/md/raid5.c
- Card: cards/CVE-2024-26756.md

- 补丁主题: md: Don't register sync_thread for reshape directly
- 代码上下文: static void md_start_sync(struct work_struct *ws), static int raid10_run(struct mddev *mddev), out:, static int raid5_run(struct mddev *mddev), static int raid5_start_reshape(struct mddev *mddev)
- 建议落地动作:
  - 在 `drivers/md/md.c` 的 `static void md_start_sync(struct work_struct *ws)` 上下文中新增 `char *name;`。
  - 在 `drivers/md/md.c` 的 `static void md_start_sync(struct work_struct *ws)` 上下文中将 `md_register_thread(md_do_sync, mddev, "resync"));` 调整为 `name = test_bit(MD_RECOVERY_RESHAPE, &mddev->recovery) ?`。
  - 在 `drivers/md/raid10.c` 的 `static int raid10_run(struct mddev *mddev)` 上下文中将 `set_bit(MD_RECOVERY_RUNNING, &mddev->recovery);` 调整为 `set_bit(MD_RECOVERY_NEEDED, &mddev->recovery);`。
  - 在 `drivers/md/raid10.c` 的 `out:` 上下文中将 `set_bit(MD_RECOVERY_RUNNING, &mddev->recovery);` 调整为 `set_bit(MD_RECOVERY_NEEDED, &mddev->recovery);`。

## CVE-2024-26757
- Title: md: Don't ignore read-only array in md_check_recovery()
- Affected files: drivers/md/md.c
- Card: cards/CVE-2024-26757.md

- 补丁主题: md: Don't ignore read-only array in md_check_recovery()
- 代码上下文: not_running:, void md_check_recovery(struct mddev *mddev)
- 建议落地动作:
  - 在 `drivers/md/md.c` 中调整 `clear_bit()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/md/md.c` 的 `not_running:` 上下文中新增 `static void unregister_sync_thread(struct mddev *mddev)`。
  - 在 `drivers/md/md.c` 的 `void md_check_recovery(struct mddev *mddev)` 上下文中将 `!test_bit(MD_RECOVERY_NEEDED, &mddev->recovery))` 调整为 `!test_bit(MD_RECOVERY_NEEDED, &mddev->recovery) &&`。
  - 在 `drivers/md/md.c` 的 `void md_check_recovery(struct mddev *mddev)` 上下文中将 `/* sync_work already queued. */` 调整为 `unregister_sync_thread(mddev);`。

## CVE-2024-26758
- Title: md: Don't ignore suspended array in md_check_recovery()
- Affected files: drivers/md/md.c
- Card: cards/CVE-2024-26758.md

- 补丁主题: md: Don't ignore suspended array in md_check_recovery()
- 代码上下文: not_running:
- 建议落地动作:
  - 在 `drivers/md/md.c` 的 `not_running:` 上下文中移除 `if (READ_ONCE(mddev->suspended))`。

## CVE-2024-26759
- Title: mm/swap: fix race when skipping swapcache
- Affected files: include/linux/swap.h, mm/memory.c, mm/swap.h, mm/swapfile.c
- Card: cards/CVE-2024-26759.md

- 补丁主题: mm/swap: fix race when skipping swapcache
- 代码上下文: static inline int swap_duplicate(swp_entry_t swp), vm_fault_t do_swap_page(struct vm_fault *vmf), unlock:, out_release:, void __delete_from_swap_cache(struct folio *folio,, static inline int swap_writepage(struct page *p, struct writeback_control *wbc), int swapcache_prepare(swp_entry_t entry)
- 建议落地动作:
  - 在 `include/linux/swap.h` 的 `static inline int swap_duplicate(swp_entry_t swp)` 上下文中新增 `static inline int swapcache_prepare(swp_entry_t swp)`。
  - 在 `mm/memory.c` 的 `vm_fault_t do_swap_page(struct vm_fault *vmf)` 上下文中新增 `bool need_clear_cache = false;`。
  - 在 `mm/memory.c` 的 `vm_fault_t do_swap_page(struct vm_fault *vmf)` 上下文中新增 `* Prevent parallel swapin from proceeding with`。
  - 在 `mm/memory.c` 的 `unlock:` 上下文中新增 `/* Clear the swap cache pin for direct swapin after PTL unlock */`。

## CVE-2024-26760
- Title: scsi: target: pscsi: Fix bio_put() for error case
- Affected files: drivers/target/target_core_pscsi.c
- Card: cards/CVE-2024-26760.md

- 补丁主题: scsi: target: pscsi: Fix bio_put() for error case
- 代码上下文: new_bio:
- 建议落地动作:
  - 在 `drivers/target/target_core_pscsi.c` 的 `new_bio:` 上下文中将 `if (bio)` 调整为 `if (bio) {`。

## CVE-2024-26761
- Title: cxl/pci: Fix disabling memory if DVSEC CXL Range does not match a CFMWS window
- Affected files: drivers/cxl/core/pci.c
- Card: cards/CVE-2024-26761.md

- 补丁主题: cxl/pci: Fix disabling memory if DVSEC CXL Range does not match a
- 代码上下文: static bool __cxl_hdm_decode_init(struct cxl_dev_state *cxlds,
- 建议落地动作:
  - 在 `drivers/cxl/core/pci.c` 的 `static bool __cxl_hdm_decode_init(struct cxl_dev_state *cxlds,` 上下文中将 `if (!allowed) {` 调整为 `if (!allowed && info->mem_enabled) {`。

## CVE-2024-26762
- Title: cxl/pci: Skip to handle RAS errors if CXL.mem device is detached
- Affected files: drivers/cxl/core/pci.c
- Card: cards/CVE-2024-26762.md

- 补丁主题: cxl/pci: Skip to handle RAS errors if CXL.mem device is detached
- 代码上下文: static void cxl_handle_rdport_errors(struct cxl_dev_state *cxlds) { }, pci_ers_result_t cxl_error_detected(struct pci_dev *pdev,
- 建议落地动作:
  - 在 `drivers/cxl/core/pci.c` 中调整 `cxl_handle_rdport_errors()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/cxl/core/pci.c` 的 `static void cxl_handle_rdport_errors(struct cxl_dev_state *cxlds) { }` 上下文中将 `if (cxlds->rcd)` 调整为 `struct device *dev = &cxlds->cxlmd->dev;`。
  - 在 `drivers/cxl/core/pci.c` 的 `pci_ers_result_t cxl_error_detected(struct pci_dev *pdev,` 上下文中将 `if (cxlds->rcd)` 调整为 `scoped_guard(device, dev) {`。

## CVE-2024-26763
- Title: dm-crypt: don't modify the data when using authenticated encryption
- Affected files: drivers/md/dm-crypt.c
- Card: cards/CVE-2024-26763.md

- 补丁主题: dm-crypt: don't modify the data when using authenticated encryption
- 代码上下文: static void kcryptd_crypt_write_convert(struct dm_crypt_io *io)
- 建议落地动作:
  - 在 `drivers/md/dm-crypt.c` 的 `static void kcryptd_crypt_write_convert(struct dm_crypt_io *io)` 上下文中新增 `if (crypt_integrity_aead(cc)) {`。

## CVE-2024-26764
- Title: fs/aio: Restrict kiocb_set_cancel_fn() to I/O submitted via libaio
- Affected files: fs/aio.c, include/linux/fs.h
- Card: cards/CVE-2024-26764.md

- 补丁主题: fs/aio: Restrict kiocb_set_cancel_fn() to I/O submitted via libaio
- 代码上下文: void kiocb_set_cancel_fn(struct kiocb *iocb, kiocb_cancel_fn *cancel), static int aio_prep_rw(struct kiocb *req, const struct iocb *iocb), enum rw_hint {
- 建议落地动作:
  - 在 `fs/aio.c` 的 `void kiocb_set_cancel_fn(struct kiocb *iocb, kiocb_cancel_fn *cancel)` 上下文中新增 `* kiocb didn't come from aio or is neither a read nor a write, hence`。
  - 在 `fs/aio.c` 的 `static int aio_prep_rw(struct kiocb *req, const struct iocb *iocb)` 上下文中将 `req->ki_flags = req->ki_filp->f_iocb_flags;` 调整为 `req->ki_flags = req->ki_filp->f_iocb_flags | IOCB_AIO_RW;`。
  - 在 `include/linux/fs.h` 的 `enum rw_hint {` 上下文中新增 `/* kiocb is a read or write operation submitted by fs/aio.c. */`。

## CVE-2024-26765
- Title: LoongArch: Disable IRQ before init_fn() for nonboot CPUs
- Affected files: arch/loongarch/kernel/smp.c
- Card: cards/CVE-2024-26765.md

- 补丁主题: LoongArch: Disable IRQ before init_fn() for nonboot CPUs
- 代码上下文: void __noreturn arch_cpu_idle_dead(void)
- 建议落地动作:
  - 在 `arch/loongarch/kernel/smp.c` 的 `void __noreturn arch_cpu_idle_dead(void)` 上下文中新增 `local_irq_disable();`。

## CVE-2024-26766
- Title: IB/hfi1: Fix sdma.h tx->num_descs off-by-one error
- Affected files: drivers/infiniband/hw/hfi1/sdma.c
- Card: cards/CVE-2024-26766.md

- 补丁主题: IB/hfi1: Fix sdma.h tx->num_descs off-by-one error
- 代码上下文: int _pad_sdma_tx_descs(struct hfi1_devdata *dd, struct sdma_txreq *tx)
- 建议落地动作:
  - 在 `drivers/infiniband/hw/hfi1/sdma.c` 的 `int _pad_sdma_tx_descs(struct hfi1_devdata *dd, struct sdma_txreq *tx)` 上下文中将 `if ((unlikely(tx->num_desc + 1 == tx->desc_limit))) {` 调整为 `if ((unlikely(tx->num_desc == tx->desc_limit))) {`。

## CVE-2024-26767
- Title: drm/amd/display: fixed integer types and null check locations
- Affected files: drivers/gpu/drm/amd/display/dc/bios/bios_parser2.c, drivers/gpu/drm/amd/display/dc/link/link_validation.c
- Card: cards/CVE-2024-26767.md

- 补丁主题: drm/amd/display: fixed integer types and null check locations
- 代码上下文: static enum bp_result get_firmware_info_v3_2(, static enum bp_result get_integrated_info_v11(, static enum bp_result get_integrated_info_v2_1(, static enum bp_result get_integrated_info_v2_2(, bool link_validate_dpia_bandwidth(const struct dc_stream_state *stream, const un
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/bios/bios_parser2.c` 中调整 `DC_LOG_BIOS()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/gpu/drm/amd/display/dc/bios/bios_parser2.c` 的 `static enum bp_result get_firmware_info_v3_2(` 上下文中调整 `DC_LOG_BIOS()` 的调用位置，使其与新的初始化顺序保持一致。
  - 在 `drivers/gpu/drm/amd/display/dc/bios/bios_parser2.c` 的 `static enum bp_result get_integrated_info_v11(` 上下文中调整 `DC_LOG_BIOS()` 的调用位置，使其与新的初始化顺序保持一致。
  - 在 `drivers/gpu/drm/amd/display/dc/bios/bios_parser2.c` 的 `static enum bp_result get_integrated_info_v2_1(` 上下文中调整 `DC_LOG_BIOS()` 的调用位置，使其与新的初始化顺序保持一致。

## CVE-2024-26768
- Title: LoongArch: Change acpi_core_pic[NR_CPUS] to acpi_core_pic[MAX_CORE_PIC]
- Affected files: arch/loongarch/include/asm/acpi.h, arch/loongarch/kernel/acpi.c
- Card: cards/CVE-2024-26768.md

- 补丁主题: LoongArch: Change acpi_core_pic[NR_CPUS] to
- 代码上下文: static inline bool acpi_has_cpu_in_madt(void), int disabled_cpus;
- 建议落地动作:
  - 在 `arch/loongarch/include/asm/acpi.h` 的 `static inline bool acpi_has_cpu_in_madt(void)` 上下文中将 `extern struct acpi_madt_core_pic acpi_core_pic[NR_CPUS];` 调整为 `#define MAX_CORE_PIC 256`。
  - 在 `arch/loongarch/kernel/acpi.c` 的 `int disabled_cpus;` 上下文中将 `#define MAX_CORE_PIC 256` 调整为 `struct acpi_madt_core_pic acpi_core_pic[MAX_CORE_PIC];`。

## CVE-2024-26769
- Title: nvmet-fc: avoid deadlock on delete association path
- Affected files: drivers/nvme/target/fc.c
- Card: cards/CVE-2024-26769.md

- 补丁主题: nvmet-fc: avoid deadlock on delete association path
- 代码上下文: struct nvmet_fc_tgtport {, static int nvmet_fc_tgt_a_get(struct nvmet_fc_tgt_assoc *assoc);, __nvmet_fc_finish_ls_req(struct nvmet_fc_ls_req_op *lsop), nvmet_fc_register_targetport(struct nvmet_fc_port_info *pinfo,
- 建议落地动作:
  - 在 `drivers/nvme/target/fc.c` 中调整 `nvmet_fc_tgtport_put()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/nvme/target/fc.c` 的 `struct nvmet_fc_tgtport {` 上下文中新增 `struct work_struct put_work;`。
  - 在 `drivers/nvme/target/fc.c` 的 `static int nvmet_fc_tgt_a_get(struct nvmet_fc_tgt_assoc *assoc);` 上下文中新增 `static void nvmet_fc_put_tgtport_work(struct work_struct *work)`。
  - 在 `drivers/nvme/target/fc.c` 的 `__nvmet_fc_finish_ls_req(struct nvmet_fc_ls_req_op *lsop)` 上下文中将 `goto out_puttgtport;` 调整为 `goto out_putwork;`。

## CVE-2024-26770
- Title: HID: nvidia-shield: Add missing null pointer checks to LED initialization
- Affected files: drivers/hid/hid-nvidia-shield.c
- Card: cards/CVE-2024-26770.md

- 补丁主题: HID: nvidia-shield: Add missing null pointer checks to LED
- 代码上下文: static inline int thunderstrike_led_create(struct thunderstrike *ts), static inline int thunderstrike_psy_create(struct shield_device *shield_dev)
- 建议落地动作:
  - 在 `drivers/hid/hid-nvidia-shield.c` 的 `static inline int thunderstrike_led_create(struct thunderstrike *ts)` 上下文中新增 `if (!led->name)`。
  - 在 `drivers/hid/hid-nvidia-shield.c` 的 `static inline int thunderstrike_psy_create(struct shield_device *shield_dev)` 上下文中新增 `if (!shield_dev->battery_dev.desc.name)`。

## CVE-2024-26771
- Title: dmaengine: ti: edma: Add some null pointer checks to the edma_probe
- Affected files: drivers/dma/ti/edma.c
- Card: cards/CVE-2024-26771.md

- 补丁主题: dmaengine: ti: edma: Add some null pointer checks to the edma_probe
- 代码上下文: static int edma_probe(struct platform_device *pdev)
- 建议落地动作:
  - 在 `drivers/dma/ti/edma.c` 的 `static int edma_probe(struct platform_device *pdev)` 上下文中新增 `if (!irq_name) {`。

## CVE-2024-26772
- Title: ext4: avoid allocating blocks from corrupted group in ext4_mb_find_by_goal()
- Affected files: fs/ext4/mballoc.c
- Card: cards/CVE-2024-26772.md

- 补丁主题: ext4: avoid allocating blocks from corrupted group in
- 代码上下文: int ext4_mb_find_by_goal(struct ext4_allocation_context *ac,
- 建议落地动作:
  - 在 `fs/ext4/mballoc.c` 的 `int ext4_mb_find_by_goal(struct ext4_allocation_context *ac,` 上下文中将 `if (unlikely(EXT4_MB_GRP_BBITMAP_CORRUPT(e4b->bd_info))) {` 调整为 `if (unlikely(EXT4_MB_GRP_BBITMAP_CORRUPT(e4b->bd_info)))`。
  - 在 `fs/ext4/mballoc.c` 的 `int ext4_mb_find_by_goal(struct ext4_allocation_context *ac,` 上下文中新增 `out:`。

## CVE-2024-26773
- Title: ext4: avoid allocating blocks from corrupted group in ext4_mb_try_best_found()
- Affected files: fs/ext4/mballoc.c
- Card: cards/CVE-2024-26773.md

- 补丁主题: ext4: avoid allocating blocks from corrupted group in
- 代码上下文: void ext4_mb_try_best_found(struct ext4_allocation_context *ac,
- 建议落地动作:
  - 在 `fs/ext4/mballoc.c` 的 `void ext4_mb_try_best_found(struct ext4_allocation_context *ac,` 上下文中新增 `if (unlikely(EXT4_MB_GRP_BBITMAP_CORRUPT(e4b->bd_info)))`。
  - 在 `fs/ext4/mballoc.c` 的 `void ext4_mb_try_best_found(struct ext4_allocation_context *ac,` 上下文中新增 `out:`。

## CVE-2024-26774
- Title: ext4: avoid dividing by 0 in mb_update_avg_fragment_size() when block bitmap corrupt
- Affected files: fs/ext4/mballoc.c
- Card: cards/CVE-2024-26774.md

- 补丁主题: ext4: avoid dividing by 0 in mb_update_avg_fragment_size() when block
- 代码上下文: mb_update_avg_fragment_size(struct super_block *sb, struct ext4_group_info *grp)
- 建议落地动作:
  - 在 `fs/ext4/mballoc.c` 的 `mb_update_avg_fragment_size(struct super_block *sb, struct ext4_group_info *grp)` 上下文中将 `if (!test_opt2(sb, MB_OPTIMIZE_SCAN) || grp->bb_free == 0)` 调整为 `if (!test_opt2(sb, MB_OPTIMIZE_SCAN) || grp->bb_fragments == 0)`。

## CVE-2024-26775
- Title: aoe: avoid potential deadlock at set_capacity
- Affected files: drivers/block/aoe/aoeblk.c
- Card: cards/CVE-2024-26775.md

- 补丁主题: aoe: avoid potential deadlock at set_capacity
- 代码上下文: aoeblk_gdalloc(void *vp)
- 建议落地动作:
  - 在 `drivers/block/aoe/aoeblk.c` 的 `aoeblk_gdalloc(void *vp)` 上下文中新增 `sector_t ssize;`。
  - 在 `drivers/block/aoe/aoeblk.c` 的 `aoeblk_gdalloc(void *vp)` 上下文中将 `set_capacity(gd, d->ssize);` 调整为 `ssize = d->ssize;`。
  - 在 `drivers/block/aoe/aoeblk.c` 的 `aoeblk_gdalloc(void *vp)` 上下文中新增 `set_capacity(gd, ssize);`。

## CVE-2024-26776
- Title: spi: hisi-sfc-v3xx: Return IRQ_NONE if no interrupts were detected
- Affected files: drivers/spi/spi-hisi-sfc-v3xx.c
- Card: cards/CVE-2024-26776.md

- 补丁主题: spi: hisi-sfc-v3xx: Return IRQ_NONE if no interrupts were detected
- 代码上下文: static const struct spi_controller_mem_ops hisi_sfc_v3xx_mem_ops = {
- 建议落地动作:
  - 在 `drivers/spi/spi-hisi-sfc-v3xx.c` 的 `static const struct spi_controller_mem_ops hisi_sfc_v3xx_mem_ops = {` 上下文中新增 `u32 reg;`。

## CVE-2024-26777
- Title: fbdev: sis: Error out if pixclock equals zero
- Affected files: drivers/video/fbdev/sis/sis_main.c
- Card: cards/CVE-2024-26777.md

- 补丁主题: fbdev: sis: Error out if pixclock equals zero
- 代码上下文: sisfb_check_var(struct fb_var_screeninfo *var, struct fb_info *info)
- 建议落地动作:
  - 在 `drivers/video/fbdev/sis/sis_main.c` 的 `sisfb_check_var(struct fb_var_screeninfo *var, struct fb_info *info)` 上下文中新增 `if (!var->pixclock)`。

## CVE-2024-26778
- Title: fbdev: savage: Error out if pixclock equals zero
- Affected files: drivers/video/fbdev/savage/savagefb_driver.c
- Card: cards/CVE-2024-26778.md

- 补丁主题: fbdev: savage: Error out if pixclock equals zero
- 代码上下文: static int savagefb_check_var(struct fb_var_screeninfo   *var,
- 建议落地动作:
  - 在 `drivers/video/fbdev/savage/savagefb_driver.c` 的 `static int savagefb_check_var(struct fb_var_screeninfo   *var,` 上下文中新增 `if (!var->pixclock)`。

## CVE-2024-26779
- Title: wifi: mac80211: fix race condition on enabling fast-xmit
- Affected files: net/mac80211/sta_info.c, net/mac80211/tx.c
- Card: cards/CVE-2024-26779.md

- 补丁主题: wifi: mac80211: fix race condition on enabling fast-xmit
- 代码上下文: static int sta_info_insert_finish(struct sta_info *sta) __acquires(RCU), void ieee80211_check_fast_xmit(struct sta_info *sta)
- 建议落地动作:
  - 在 `net/mac80211/sta_info.c` 的 `static int sta_info_insert_finish(struct sta_info *sta) __acquires(RCU)` 上下文中新增 `ieee80211_check_fast_xmit(sta);`。
  - 在 `net/mac80211/tx.c` 的 `void ieee80211_check_fast_xmit(struct sta_info *sta)` 上下文中将 `if (!test_sta_flag(sta, WLAN_STA_AUTHORIZED))` 调整为 `if (!test_sta_flag(sta, WLAN_STA_AUTHORIZED) || !sta->uploaded)`。

## CVE-2024-26780
- Title: af_unix: Fix task hung while purging oob_skb in GC.
- Affected files: net/unix/garbage.c
- Card: cards/CVE-2024-26780.md

- 补丁主题: af_unix: Fix task hung while purging oob_skb in GC.
- 代码上下文: void unix_gc(void)
- 建议落地动作:
  - 在 `net/unix/garbage.c` 的 `void unix_gc(void)` 上下文中将 `list_for_each_entry_safe(u, next, &gc_candidates, link) {` 调整为 `while (!list_empty(&gc_candidates)) {`。

## CVE-2024-26781
- Title: mptcp: fix possible deadlock in subflow diag
- Affected files: net/mptcp/diag.c
- Card: cards/CVE-2024-26781.md

- 补丁主题: mptcp: fix possible deadlock in subflow diag
- 代码上下文: static int subflow_get_info(struct sock *sk, struct sk_buff *skb)
- 建议落地动作:
  - 在 `net/mptcp/diag.c` 的 `static int subflow_get_info(struct sock *sk, struct sk_buff *skb)` 上下文中新增 `if (inet_sk_state_load(sk) == TCP_LISTEN)`。

## CVE-2024-26782
- Title: mptcp: fix double-free on socket dismantle
- Affected files: net/mptcp/protocol.c
- Card: cards/CVE-2024-26782.md

- 补丁主题: mptcp: fix double-free on socket dismantle
- 代码上下文: static struct ipv6_pinfo *mptcp_inet6_sk(const struct sock *sk), struct sock *mptcp_sk_clone_init(const struct sock *sk,
- 建议落地动作:
  - 在 `net/mptcp/protocol.c` 的 `static struct ipv6_pinfo *mptcp_inet6_sk(const struct sock *sk)` 上下文中新增 `static void mptcp_copy_ip6_options(struct sock *newsk, const struct sock *sk)`。
  - 在 `net/mptcp/protocol.c` 的 `struct sock *mptcp_sk_clone_init(const struct sock *sk,` 上下文中新增 `#if IS_ENABLED(CONFIG_MPTCP_IPV6)`。

## CVE-2024-26783
- Title: mm/vmscan: fix a bug calling wakeup_kswapd() with a wrong zone index
- Affected files: mm/migrate.c
- Card: cards/CVE-2024-26783.md

- 补丁主题: mm/vmscan: fix a bug calling wakeup_kswapd() with a wrong zone index
- 代码上下文: static int numamigrate_isolate_folio(pg_data_t *pgdat, struct folio *folio)
- 建议落地动作:
  - 在 `mm/migrate.c` 的 `static int numamigrate_isolate_folio(pg_data_t *pgdat, struct folio *folio)` 上下文中新增 `* If there are no managed zones, it should not proceed`。

## CVE-2024-26784
- Title: pmdomain: arm: Fix NULL dereference on scmi_perf_domain removal
- Affected files: drivers/pmdomain/arm/scmi_perf_domain.c
- Card: cards/CVE-2024-26784.md

- 补丁主题: pmdomain: arm: Fix NULL dereference on scmi_perf_domain removal
- 代码上下文: static void scmi_perf_domain_remove(struct scmi_device *sdev)
- 建议落地动作:
  - 在 `drivers/pmdomain/arm/scmi_perf_domain.c` 的 `static void scmi_perf_domain_remove(struct scmi_device *sdev)` 上下文中新增 `if (!scmi_pd_data)`。

## CVE-2024-26785
- Title: iommufd: Fix protection fault in iommufd_test_syz_conv_iova
- Affected files: drivers/iommu/iommufd/selftest.c
- Card: cards/CVE-2024-26785.md

- 补丁主题: iommufd: Fix protection fault in iommufd_test_syz_conv_iova
- 代码上下文: enum {, static unsigned long iommufd_test_syz_conv_iova(struct io_pagetable *iopt,, void iommufd_test_syz_conv_iova_id(struct iommufd_ucmd *ucmd,, static int iommufd_test_access_pages(struct iommufd_ucmd *ucmd,, static int iommufd_test_access_rw(struct iommufd_ucmd *ucmd,
- 建议落地动作:
  - 在 `drivers/iommu/iommufd/selftest.c` 的 `enum {` 上下文中将 `static unsigned long iommufd_test_syz_conv_iova(struct io_pagetable *iopt,` 调整为 `static unsigned long __iommufd_test_syz_conv_iova(struct io_pagetable *iopt,`。
  - 在 `drivers/iommu/iommufd/selftest.c` 的 `static unsigned long iommufd_test_syz_conv_iova(struct io_pagetable *iopt,` 上下文中新增 `static unsigned long iommufd_test_syz_conv_iova(struct iommufd_access *access,`。
  - 在 `drivers/iommu/iommufd/selftest.c` 的 `void iommufd_test_syz_conv_iova_id(struct iommufd_ucmd *ucmd,` 上下文中将 `*iova = iommufd_test_syz_conv_iova(&ioas->iopt, iova);` 调整为 `*iova = __iommufd_test_syz_conv_iova(&ioas->iopt, iova);`。
  - 在 `drivers/iommu/iommufd/selftest.c` 的 `static int iommufd_test_access_pages(struct iommufd_ucmd *ucmd,` 上下文中将 `iova = iommufd_test_syz_conv_iova(&staccess->access->ioas->iopt,` 调整为 `iova = iommufd_test_syz_conv_iova(staccess->access,`。

## CVE-2024-26786
- Title: iommufd: Fix iopt_access_list_id overwrite bug
- Affected files: drivers/iommu/iommufd/io_pagetable.c
- Card: cards/CVE-2024-26786.md

- 补丁主题: iommufd: Fix iopt_access_list_id overwrite bug
- 代码上下文: out_unlock:
- 建议落地动作:
  - 在 `drivers/iommu/iommufd/io_pagetable.c` 的 `out_unlock:` 上下文中将 `rc = xa_alloc(&iopt->access_list, &access->iopt_access_list_id, access,` 调整为 `u32 new_id;`。

## CVE-2024-26787
- Title: mmc: mmci: stm32: fix DMA API overlapping mappings warning
- Affected files: drivers/mmc/host/mmci_stm32_sdmmc.c
- Card: cards/CVE-2024-26787.md

- 补丁主题: mmc: mmci: stm32: fix DMA API overlapping mappings warning
- 代码上下文: static int sdmmc_idma_start(struct mmci_host *host, unsigned int *datactrl), static struct mmci_host_ops sdmmc_variant_ops = {
- 建议落地动作:
  - 在 `drivers/mmc/host/mmci_stm32_sdmmc.c` 的 `static int sdmmc_idma_start(struct mmci_host *host, unsigned int *datactrl)` 上下文中新增 `host->dma_in_progress = true;`。
  - 在 `drivers/mmc/host/mmci_stm32_sdmmc.c` 的 `static int sdmmc_idma_start(struct mmci_host *host, unsigned int *datactrl)` 上下文中新增 `static void sdmmc_idma_error(struct mmci_host *host)`。
  - 在 `drivers/mmc/host/mmci_stm32_sdmmc.c` 的 `static struct mmci_host_ops sdmmc_variant_ops = {` 上下文中新增 `.dma_error = sdmmc_idma_error,`。

## CVE-2024-26788
- Title: dmaengine: fsl-qdma: init irq after reg initialization
- Affected files: drivers/dma/fsl-qdma.c
- Card: cards/CVE-2024-26788.md

- 补丁主题: dmaengine: fsl-qdma: init irq after reg initialization
- 代码上下文: static int fsl_qdma_probe(struct platform_device *pdev)
- 建议落地动作:
  - 在 `drivers/dma/fsl-qdma.c` 的 `static int fsl_qdma_probe(struct platform_device *pdev)` 上下文中调整 `fsl_qdma_irq_init()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/dma/fsl-qdma.c` 的 `static int fsl_qdma_probe(struct platform_device *pdev)` 上下文中移除 `ret = fsl_qdma_irq_init(pdev, fsl_qdma);`。
  - 在 `drivers/dma/fsl-qdma.c` 的 `static int fsl_qdma_probe(struct platform_device *pdev)` 上下文中为 `fsl_qdma_reg_init()` 增加返回值检查，失败时立即退出，避免后续流程在未完成初始化时继续执行。

## CVE-2024-26789
- Title: crypto: arm64/neonbs - fix out-of-bounds access on short input
- Affected files: arch/arm64/crypto/aes-neonbs-glue.c
- Card: cards/CVE-2024-26789.md

- 补丁主题: crypto: arm64/neonbs - fix out-of-bounds access on short input
- 代码上下文: static int ctr_encrypt(struct skcipher_request *req)
- 建议落地动作:
  - 在 `arch/arm64/crypto/aes-neonbs-glue.c` 的 `static int ctr_encrypt(struct skcipher_request *req)` 上下文中新增 `u8 buf[AES_BLOCK_SIZE];`。

## CVE-2024-26790
- Title: dmaengine: fsl-qdma: fix SoC may hang on 16 byte unaligned read
- Affected files: drivers/dma/fsl-qdma.c
- Card: cards/CVE-2024-26790.md

- 补丁主题: dmaengine: fsl-qdma: fix SoC may hang on 16 byte unaligned read
- 代码上下文: static void fsl_qdma_comp_fill_memcpy(struct fsl_qdma_comp *fsl_comp,
- 建议落地动作:
  - 在 `drivers/dma/fsl-qdma.c` 的 `global` 上下文中新增 `#define FSL_QDMA_CMD_PF BIT(17)`。
  - 在 `drivers/dma/fsl-qdma.c` 的 `static void fsl_qdma_comp_fill_memcpy(struct fsl_qdma_comp *fsl_comp,` 上下文中将 `FSL_QDMA_CMD_RWTTYPE_OFFSET);` 调整为 `FSL_QDMA_CMD_RWTTYPE_OFFSET) |`。

## CVE-2024-26791
- Title: btrfs: dev-replace: properly validate device names
- Affected files: fs/btrfs/dev-replace.c
- Card: cards/CVE-2024-26791.md

- 补丁主题: btrfs: dev-replace: properly validate device names
- 代码上下文: leave:, int btrfs_dev_replace_by_ioctl(struct btrfs_fs_info *fs_info,
- 建议落地动作:
  - 在 `fs/btrfs/dev-replace.c` 的 `leave:` 上下文中新增 `static int btrfs_check_replace_dev_names(struct btrfs_ioctl_dev_replace_args *args)`。
  - 在 `fs/btrfs/dev-replace.c` 的 `int btrfs_dev_replace_by_ioctl(struct btrfs_fs_info *fs_info,` 上下文中为 `btrfs_check_replace_dev_names()` 增加返回值检查，失败时立即退出，避免后续流程在未完成初始化时继续执行。

## CVE-2024-26792
- Title: btrfs: fix double free of anonymous device after snapshot creation failure
- Affected files: fs/btrfs/disk-io.c, fs/btrfs/disk-io.h, fs/btrfs/ioctl.c, fs/btrfs/transaction.c
- Card: cards/CVE-2024-26792.md

- 补丁主题: btrfs: fix double free of anonymous device after snapshot creation
- 代码上下文: void btrfs_free_fs_info(struct btrfs_fs_info *fs_info), again:, fail:, struct btrfs_root *btrfs_get_fs_root(struct btrfs_fs_info *fs_info,, void btrfs_free_fs_roots(struct btrfs_fs_info *fs_info);, static noinline int create_subvol(struct user_namespace *mnt_userns,, static noinline int create_pending_snapshot(struct btrfs_trans_handle *trans,
- 建议落地动作:
  - 在 `fs/btrfs/disk-io.c` 的 `void btrfs_free_fs_info(struct btrfs_fs_info *fs_info)` 上下文中将 `* pass 0 for new allocation.` 调整为 `* pass NULL for a new allocation.`。
  - 在 `fs/btrfs/disk-io.c` 的 `again:` 上下文中将 `if (unlikely(anon_dev)) {` 调整为 `if (unlikely(anon_dev && *anon_dev)) {`。
  - 在 `fs/btrfs/disk-io.c` 的 `again:` 上下文中将 `ret = btrfs_init_fs_root(root, anon_dev);` 调整为 `ret = btrfs_init_fs_root(root, anon_dev ? *anon_dev : 0);`。
  - 在 `fs/btrfs/disk-io.c` 的 `fail:` 上下文中将 `if (anon_dev)` 调整为 `if (anon_dev && *anon_dev)`。

## CVE-2024-26793
- Title: gtp: fix use-after-free and null-ptr-deref in gtp_newlink()
- Affected files: drivers/net/gtp.c
- Card: cards/CVE-2024-26793.md

- 补丁主题: gtp: fix use-after-free and null-ptr-deref in gtp_newlink()
- 代码上下文: static int __init gtp_init(void)
- 建议落地动作:
  - 在 `drivers/net/gtp.c` 的 `static int __init gtp_init(void)` 上下文中调整 `rtnl_link_register()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/net/gtp.c` 的 `static int __init gtp_init(void)` 上下文中将 `err = rtnl_link_register(&gtp_link_ops);` 调整为 `err = register_pernet_subsys(&gtp_net_ops);`。

## CVE-2024-26795
- Title: riscv: Sparse-Memory/vmemmap out-of-bounds fix
- Affected files: arch/riscv/include/asm/pgtable.h
- Card: cards/CVE-2024-26795.md

- 补丁主题: riscv: Sparse-Memory/vmemmap out-of-bounds fix
- 代码上下文: 未解析出 hunk 上下文
- 建议落地动作:
  - 在 `arch/riscv/include/asm/pgtable.h` 的 `global` 上下文中将 `#define vmemmap ((struct page *)VMEMMAP_START)` 调整为 `#define vmemmap ((struct page *)VMEMMAP_START - (phys_ram_base >> PAGE_SHIFT))`。

## CVE-2024-26796
- Title: drivers: perf: ctr_get_width function for legacy is not defined
- Affected files: drivers/perf/riscv_pmu.c, drivers/perf/riscv_pmu_legacy.c
- Card: cards/CVE-2024-26796.md

- 补丁主题: drivers: perf: ctr_get_width function for legacy is not defined
- 代码上下文: u64 riscv_pmu_ctr_get_width_mask(struct perf_event *event), static int pmu_legacy_event_map(struct perf_event *event, u64 *config), static void pmu_legacy_init(struct riscv_pmu *pmu)
- 建议落地动作:
  - 在该补丁中调整 `ctr_get_width()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/perf/riscv_pmu.c` 的 `u64 riscv_pmu_ctr_get_width_mask(struct perf_event *event)` 上下文中将 `if (!rvpmu->ctr_get_width)` 调整为 `if (hwc->idx == -1)`。
  - 在 `drivers/perf/riscv_pmu_legacy.c` 的 `static int pmu_legacy_event_map(struct perf_event *event, u64 *config)` 上下文中新增 `/* cycle & instret are always 64 bit, one bit less according to SBI spec */`。
  - 在 `drivers/perf/riscv_pmu_legacy.c` 的 `static void pmu_legacy_init(struct riscv_pmu *pmu)` 上下文中将 `pmu->ctr_get_width = NULL;` 调整为 `pmu->ctr_get_width = pmu_legacy_ctr_get_width;`。

## CVE-2024-26797
- Title: drm/amd/display: Prevent potential buffer overflow in map_hw_resources
- Affected files: drivers/gpu/drm/amd/display/dc/dml2/dml2_wrapper.c
- Card: cards/CVE-2024-26797.md

- 补丁主题: drm/amd/display: Prevent potential buffer overflow in
- 代码上下文: static void map_hw_resources(struct dml2_context *dml2,
- 建议落地动作:
  - 在 `drivers/gpu/drm/amd/display/dc/dml2/dml2_wrapper.c` 的 `static void map_hw_resources(struct dml2_context *dml2,` 上下文中新增 `if (i >= __DML2_WRAPPER_MAX_STREAMS_PLANES__) {`。

## CVE-2024-26798
- Title: fbcon: always restore the old font data in fbcon_do_set_font()
- Affected files: drivers/video/fbdev/core/fbcon.c
- Card: cards/CVE-2024-26798.md

- 补丁主题: fbcon: always restore the old font data in fbcon_do_set_font()
- 代码上下文: static int fbcon_do_set_font(struct vc_data *vc, int w, int h, int charcount,
- 建议落地动作:
  - 在 `drivers/video/fbdev/core/fbcon.c` 的 `static int fbcon_do_set_font(struct vc_data *vc, int w, int h, int charcount,` 上下文中将 `char *old_data = NULL;` 调整为 `u8 *old_data = vc->vc_font.data;`。
  - 在 `drivers/video/fbdev/core/fbcon.c` 的 `static int fbcon_do_set_font(struct vc_data *vc, int w, int h, int charcount,` 上下文中将 `if (old_data && (--REFCOUNT(old_data) == 0))` 调整为 `if (old_userfont && (--REFCOUNT(old_data) == 0))`。

## CVE-2024-26799
- Title: ASoC: qcom: Fix uninitialized pointer dmactl
- Affected files: sound/soc/qcom/lpass-cdc-dma.c
- Card: cards/CVE-2024-26799.md

- 补丁主题: ASoC: qcom: Fix uninitialized pointer dmactl
- 代码上下文: static int lpass_cdc_dma_daiops_trigger(struct snd_pcm_substream *substream,
- 建议落地动作:
  - 在 `sound/soc/qcom/lpass-cdc-dma.c` 的 `static int lpass_cdc_dma_daiops_trigger(struct snd_pcm_substream *substream,` 上下文中将 `struct lpaif_dmactl *dmactl;` 调整为 `struct lpaif_dmactl *dmactl = NULL;`。

## CVE-2024-26800
- Title: tls: fix use-after-free on failed backlog decryption
- Affected files: net/tls/tls_sw.c
- Card: cards/CVE-2024-26800.md

- 补丁主题: tls: fix use-after-free on failed backlog decryption
- 代码上下文: struct tls_decrypt_arg {, static int tls_do_decryption(struct sock *sk,, static int tls_decrypt_sg(struct sock *sk, struct iov_iter *out_iov,
- 建议落地动作:
  - 在 `net/tls/tls_sw.c` 中调整 `atomic_dec()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/tls/tls_sw.c` 的 `struct tls_decrypt_arg {` 上下文中新增 `bool async_done;`。
  - 在 `net/tls/tls_sw.c` 的 `static int tls_do_decryption(struct sock *sk,` 上下文中将 `ret = ret ?: -EINPROGRESS;` 调整为 `if (ret == -EINPROGRESS)`。
  - 在 `net/tls/tls_sw.c` 的 `static int tls_decrypt_sg(struct sock *sk, struct iov_iter *out_iov,` 上下文中将 `if (err)` 调整为 `if (err) {`。

## CVE-2024-26801
- Title: Bluetooth: Avoid potential use-after-free in hci_error_reset
- Affected files: net/bluetooth/hci_core.c
- Card: cards/CVE-2024-26801.md

- 补丁主题: Bluetooth: Avoid potential use-after-free in hci_error_reset
- 代码上下文: static void hci_error_reset(struct work_struct *work)
- 建议落地动作:
  - 在 `net/bluetooth/hci_core.c` 的 `static void hci_error_reset(struct work_struct *work)` 上下文中调整 `hci_dev_do_open()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/bluetooth/hci_core.c` 的 `static void hci_error_reset(struct work_struct *work)` 上下文中新增 `hci_dev_hold(hdev);`。
  - 在 `net/bluetooth/hci_core.c` 的 `static void hci_error_reset(struct work_struct *work)` 上下文中将 `if (hci_dev_do_close(hdev))` 调整为 `if (!hci_dev_do_close(hdev))`。

## CVE-2024-26802
- Title: stmmac: Clear variable when destroying workqueue
- Affected files: drivers/net/ethernet/stmicro/stmmac/stmmac_main.c
- Card: cards/CVE-2024-26802.md

- 补丁主题: stmmac: Clear variable when destroying workqueue
- 代码上下文: static void stmmac_fpe_stop_wq(struct stmmac_priv *priv)
- 建议落地动作:
  - 在 `drivers/net/ethernet/stmicro/stmmac/stmmac_main.c` 的 `static void stmmac_fpe_stop_wq(struct stmmac_priv *priv)` 上下文中将 `if (priv->fpe_wq)` 调整为 `if (priv->fpe_wq) {`。

## CVE-2024-26803
- Title: net: veth: clear GRO when clearing XDP even when down
- Affected files: drivers/net/veth.c
- Card: cards/CVE-2024-26803.md

- 补丁主题: net: veth: clear GRO when clearing XDP even when down
- 代码上下文: static int veth_enable_xdp(struct net_device *dev), static void veth_disable_xdp(struct net_device *dev), static int veth_xdp_set(struct net_device *dev, struct bpf_prog *prog,
- 建议落地动作:
  - 在 `drivers/net/veth.c` 中调整 `veth_gro_requested()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `drivers/net/veth.c` 的 `static int veth_enable_xdp(struct net_device *dev)` 上下文中移除 `if (!veth_gro_requested(dev)) {`。
  - 在 `drivers/net/veth.c` 的 `static void veth_disable_xdp(struct net_device *dev)` 上下文中将 `if (!netif_running(dev) || !veth_gro_requested(dev)) {` 调整为 `if (!netif_running(dev) || !veth_gro_requested(dev))`。
  - 在 `drivers/net/veth.c` 的 `static int veth_xdp_set(struct net_device *dev, struct bpf_prog *prog,` 上下文中新增 `if (!veth_gro_requested(dev)) {`。

## CVE-2024-26804
- Title: net: ip_tunnel: prevent perpetual headroom growth
- Affected files: net/ipv4/ip_tunnel.c
- Card: cards/CVE-2024-26804.md

- 补丁主题: net: ip_tunnel: prevent perpetual headroom growth
- 代码上下文: static int tnl_update_pmtu(struct net_device *dev, struct sk_buff *skb,, void ip_md_tunnel_xmit(struct sk_buff *skb, struct net_device *dev,, void ip_tunnel_xmit(struct sk_buff *skb, struct net_device *dev,
- 建议落地动作:
  - 在 `net/ipv4/ip_tunnel.c` 中调整 `READ_ONCE()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/ipv4/ip_tunnel.c` 的 `static int tnl_update_pmtu(struct net_device *dev, struct sk_buff *skb,` 上下文中新增 `static void ip_tunnel_adj_headroom(struct net_device *dev, unsigned int headroom)`。
  - 在 `net/ipv4/ip_tunnel.c` 的 `void ip_md_tunnel_xmit(struct sk_buff *skb, struct net_device *dev,` 上下文中将 `if (headroom > READ_ONCE(dev->needed_headroom))` 调整为 `if (skb_cow_head(skb, headroom)) {`。
  - 在 `net/ipv4/ip_tunnel.c` 的 `void ip_tunnel_xmit(struct sk_buff *skb, struct net_device *dev,` 上下文中将 `if (max_headroom > READ_ONCE(dev->needed_headroom))` 调整为 `if (skb_cow_head(skb, max_headroom)) {`。

## CVE-2024-26805
- Title: netlink: Fix kernel-infoleak-after-free in __skb_datagram_iter
- Affected files: net/netlink/af_netlink.c
- Card: cards/CVE-2024-26805.md

- 补丁主题: netlink: Fix kernel-infoleak-after-free in __skb_datagram_iter
- 代码上下文: static inline u32 netlink_group_mask(u32 group)
- 建议落地动作:
  - 在 `net/netlink/af_netlink.c` 的 `static inline u32 netlink_group_mask(u32 group)` 上下文中将 `unsigned int len = skb_end_offset(skb);` 调整为 `unsigned int len = skb->len;`。

## CVE-2024-26806
- Title: spi: cadence-qspi: remove system-wide suspend helper calls from runtime PM hooks
- Affected files: drivers/spi/spi-cadence-quadspi.c
- Card: cards/CVE-2024-26806.md

- 补丁主题: spi: cadence-qspi: remove system-wide suspend helper calls from
- 代码上下文: static void cqspi_remove(struct platform_device *pdev), static int cqspi_resume(struct device *dev)
- 建议落地动作:
  - 在 `drivers/spi/spi-cadence-quadspi.c` 的 `static void cqspi_remove(struct platform_device *pdev)` 上下文中将 `int ret;` 调整为 `return 0;`。
  - 在 `drivers/spi/spi-cadence-quadspi.c` 的 `static int cqspi_resume(struct device *dev)` 上下文中将 `return spi_controller_resume(cqspi->host);` 调整为 `return 0;`。

## CVE-2024-26807
- Title: spi: cadence-qspi: fix pointer reference in runtime PM hooks
- Affected files: drivers/spi/spi-cadence-quadspi.c
- Card: cards/CVE-2024-26807.md

- 补丁主题: spi: cadence-qspi: fix pointer reference in runtime PM hooks
- 代码上下文: static void cqspi_remove(struct platform_device *pdev), static int cqspi_suspend(struct device *dev), static int cqspi_resume(struct device *dev)
- 建议落地动作:
  - 在 `drivers/spi/spi-cadence-quadspi.c` 的 `static void cqspi_remove(struct platform_device *pdev)` 上下文中将 `struct spi_controller *host = dev_get_drvdata(dev);` 调整为 `ret = spi_controller_suspend(cqspi->host);`。
  - 在 `drivers/spi/spi-cadence-quadspi.c` 的 `static int cqspi_suspend(struct device *dev)` 上下文中移除 `struct spi_controller *host = dev_get_drvdata(dev);`。
  - 在 `drivers/spi/spi-cadence-quadspi.c` 的 `static int cqspi_resume(struct device *dev)` 上下文中将 `return spi_controller_resume(host);` 调整为 `return spi_controller_resume(cqspi->host);`。

## CVE-2024-26808
- Title: netfilter: nft_chain_filter: handle NETDEV_UNREGISTER for inet/ingress basechain
- Affected files: net/netfilter/nft_chain_filter.c
- Card: cards/CVE-2024-26808.md

- 补丁主题: netfilter: nft_chain_filter: handle NETDEV_UNREGISTER for
- 代码上下文: static int nf_tables_netdev_event(struct notifier_block *this,
- 建议落地动作:
  - 在 `net/netfilter/nft_chain_filter.c` 的 `static int nf_tables_netdev_event(struct notifier_block *this,` 上下文中将 `struct nft_table *table;` 调整为 `struct nft_base_chain *basechain;`。
  - 在 `net/netfilter/nft_chain_filter.c` 的 `static int nf_tables_netdev_event(struct notifier_block *this,` 上下文中将 `if (table->family != NFPROTO_NETDEV)` 调整为 `if (table->family != NFPROTO_NETDEV &&`。
  - 在 `net/netfilter/nft_chain_filter.c` 的 `static int nf_tables_netdev_event(struct notifier_block *this,` 上下文中新增 `basechain = nft_base_chain(chain);`。

## CVE-2024-26809
- Title: netfilter: nft_set_pipapo: release elements in clone only from destroy path
- Affected files: net/netfilter/nft_set_pipapo.c
- Card: cards/CVE-2024-26809.md

- 补丁主题: netfilter: nft_set_pipapo: release elements in clone only from
- 代码上下文: static void nft_pipapo_destroy(const struct nft_ctx *ctx,
- 建议落地动作:
  - 在 `net/netfilter/nft_set_pipapo.c` 的 `static void nft_pipapo_destroy(const struct nft_ctx *ctx,` 上下文中调整 `nft_set_pipapo_match_destroy()` 的调用顺序，使资源初始化与释放顺序保持一致。
  - 在 `net/netfilter/nft_set_pipapo.c` 的 `static void nft_pipapo_destroy(const struct nft_ctx *ctx,` 上下文中移除 `nft_set_pipapo_match_destroy(ctx, set, m);`。
  - 在 `net/netfilter/nft_set_pipapo.c` 的 `static void nft_pipapo_destroy(const struct nft_ctx *ctx,` 上下文中将 `if (priv->dirty)` 调整为 `nft_set_pipapo_match_destroy(ctx, set, m);`。
