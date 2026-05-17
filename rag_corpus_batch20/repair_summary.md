# Linux Kernel CVE Repair Summary

This file aggregates the repair guidance section from each generated knowledge card.

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

## CVE-2024-26622
- Title: tomoyo: fix UAF write bug in tomoyo_write_control()
- Affected files: security/tomoyo/common.c
- Card: cards/CVE-2024-26622.md

- 补丁主题: tomoyo: fix UAF write bug in tomoyo_write_control()
- 代码上下文: ssize_t tomoyo_write_control(struct tomoyo_io_buffer *head,
- 建议落地动作:
  - 在 `security/tomoyo/common.c` 的 `ssize_t tomoyo_write_control(struct tomoyo_io_buffer *head,` 上下文中将 `char *cp0 = head->write_buf;` 调整为 `char *cp0;`。

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

## CVE-2024-26668
- Title: netfilter: nft_limit: reject configurations that cause integer overflow
- Affected files: net/netfilter/nft_limit.c
- Card: cards/CVE-2024-26668.md

- 补丁主题: netfilter: nft_limit: reject configurations that cause integer
- 代码上下文: static inline bool nft_limit_eval(struct nft_limit_priv *priv, u64 cost), static int nft_limit_init(struct nft_limit_priv *priv,
- 建议落地动作:
  - 在 `net/netfilter/nft_limit.c` 的 `static inline bool nft_limit_eval(struct nft_limit_priv *priv, u64 cost)` 上下文中将 `u64 unit, tokens;` 调整为 `u64 unit, tokens, rate_with_burst;`。
  - 在 `net/netfilter/nft_limit.c` 的 `static int nft_limit_init(struct nft_limit_priv *priv,` 上下文中将 `if (priv->rate + priv->burst < priv->rate)` 调整为 `if (check_add_overflow(priv->rate, priv->burst, &rate_with_burst))`。

## CVE-2024-26673
- Title: netfilter: nft_ct: sanitize layer 3 and 4 protocol number in custom expectations
- Affected files: net/netfilter/nft_ct.c
- Card: cards/CVE-2024-26673.md

- 补丁主题: netfilter: nft_ct: sanitize layer 3 and 4 protocol number in custom
- 代码上下文: static int nft_ct_expect_obj_init(const struct nft_ctx *ctx,
- 建议落地动作:
  - 在 `net/netfilter/nft_ct.c` 的 `static int nft_ct_expect_obj_init(const struct nft_ctx *ctx,` 上下文中新增 `switch (priv->l3num) {`。

## CVE-2024-26726
- Title: btrfs: don't drop extent_map for free space inode on write error
- Affected files: fs/btrfs/inode.c
- Card: cards/CVE-2024-26726.md

- 补丁主题: btrfs: don't drop extent_map for free space inode on write error
- 代码上下文: out:
- 建议落地动作:
  - 在 `fs/btrfs/inode.c` 的 `out:` 上下文中将 `/* Drop extent maps for the part of the extent we didn't write. */` 调整为 `* Drop extent maps for the part of the extent we didn't write.`。
