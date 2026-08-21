# 基础设施（Infra）术语词典

> 用途：记录计算、芯片、操作系统、网络、存储、云原生与可观测性中常见的缩写和名词。解释优先服务于实验、部署和性能排查，不替代标准或厂商文档。

## 目录

- [计算与 CPU 架构](#计算与-cpu-架构)
- [操作系统与 Linux](#操作系统与-linux)
- [内存与性能](#内存与性能)
- [硬件、总线与固件](#硬件总线与固件)
- [网络基础](#网络基础)
- [RDMA、DPU 与网络卸载](#rdmadpu-与网络卸载)
- [存储](#存储)
- [虚拟化与容器](#虚拟化与容器)
- [Kubernetes 与云原生](#kubernetes-与云原生)
- [分布式系统与可靠性](#分布式系统与可靠性)
- [可观测性与性能分析](#可观测性与性能分析)
- [交付、自动化与配置管理](#交付自动化与配置管理)
- [安全](#安全)
- [AI 与加速计算](#ai-与加速计算)

---

## 计算与 CPU 架构

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| ISA | Instruction Set Architecture | 指令集架构；软件可见的机器指令、寄存器和寻址规则 | x86-64、AArch64、RISC-V 都是 ISA |
| ABI | Application Binary Interface | 二进制接口约定，如函数调用、数据布局和系统调用方式 | ABI 不兼容时二进制程序通常不能直接运行 |
| API | Application Programming Interface | 程序调用接口 | 面向源码；不要与 ABI 混淆 |
| RISC | Reduced Instruction-Set Computer | 精简指令集设计，指令通常较简单、便于流水线执行 | ARM、RISC-V 属于这一类 |
| CISC | Complex Instruction-Set Computer | 复杂指令集设计，指令长度和功能可更多样 | x86 通常归为 CISC |
| x86-64 / AMD64 | - | x86 的 64 位扩展，服务器和 PC 最常见 | Linux 中常写作 `x86_64` |
| ARM | Advanced RISC Machines | 基于 RISC 的处理器架构/IP 体系 | BlueField 的 Arm 侧属于 AArch64 |
| AArch64 / ARM64 | Advanced Architecture 64-bit | ARM 的 64 位执行状态和指令集 | 容器镜像常标为 `linux/arm64` |
| RISC-V | - | 开放标准的 RISC 指令集 | 可按扩展组合定制 |
| 微架构 | Microarchitecture | 同一 ISA 的具体实现方式 | 缓存、流水线和执行单元会不同 |
| CPU Socket | - | 主板上的一个物理 CPU 插槽 | 双路服务器有两个 socket |
| Core | CPU Core | 可独立执行指令的物理核心 | 核数不等于线程数 |
| SMT / HT | Simultaneous Multithreading / Hyper-Threading | 一个物理核同时暴露多个逻辑线程 | Intel 的实现常称 HT |
| vCPU | Virtual CPU | 分配给虚拟机或容器配额中的逻辑 CPU 单位 | 不必等同于物理核心 |
| NUMA | Non-Uniform Memory Access | 多路机器中访问本地和远端内存的延迟/带宽不同 | CPU、内存、NIC、GPU 应尽量 NUMA 对齐 |
| CPU Pinning | CPU 绑核 | 将进程、线程或虚拟机固定到指定 CPU | 减少调度迁移与抖动 |
| Affinity | 亲和性 | 进程或中断偏好运行的 CPU 集合 | 包括 CPU affinity 和 IRQ affinity |
| Context Switch | 上下文切换 | CPU 从一个任务切到另一个任务并保存/恢复状态 | 过多会增加延迟和缓存失效 |
| Interrupt / IRQ | Interrupt Request | 设备通知 CPU 处理事件的机制 | 高 PPS 网络常需调 IRQ 绑核 |
| Polling | 轮询 | CPU 主动反复检查事件而非等待中断 | 降延迟，但会占用 CPU |
| DMA | Direct Memory Access | 设备直接读写内存，CPU 不逐字节搬运 | NIC、NVMe、GPU 都大量使用 |
| IOMMU | I/O Memory Management Unit | 为 DMA 设备提供地址转换和隔离 | Intel VT-d、AMD-Vi 是常见实现 |

---

## 操作系统与 Linux

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| Kernel | 内核 | 管理 CPU、内存、设备和进程的操作系统核心 | Linux 是内核，Ubuntu 是发行版 |
| Distribution / Distro | 发行版 | 内核加软件包、安装器和默认配置的完整系统 | Ubuntu、Debian、RHEL、Rocky Linux |
| User Space | 用户态 | 普通应用运行的受限环境 | 不能直接操作硬件 |
| Kernel Space | 内核态 | 内核和驱动运行的高权限环境 | 代码缺陷可能影响整机 |
| System Call | 系统调用 | 用户程序请求内核服务的入口 | 如 `read`、`write`、`socket` |
| Process | 进程 | 正在运行的程序实例，拥有独立虚拟地址空间 | PID 是进程标识 |
| Thread | 线程 | 进程内的执行单元，通常共享地址空间 | 多线程需同步 |
| Daemon / Service | 守护进程 / 服务 | 后台长期运行的系统或业务程序 | Linux 常由 systemd 管理 |
| systemd | - | 主流 Linux 的初始化和服务管理器 | 常用 `systemctl`、`journalctl` |
| cgroup | Control Group | 对一组进程做 CPU、内存、I/O 等资源限制和统计 | 容器资源隔离的基础 |
| Namespace | 命名空间 | 隔离进程看到的资源视图 | PID、网络、挂载等命名空间 |
| PID 1 | Process Identifier 1 | 某个命名空间中的第一个进程 | 容器内需正确处理信号和僵尸进程 |
| ELF | Executable and Linkable Format | Linux 常用的可执行文件与共享库格式 | `file` 可查看架构 |
| Shared Library | 共享库 | 可在运行时被多个程序加载的库 | 常见后缀 `.so` |
| Package Manager | 包管理器 | 安装、升级、卸载软件包的工具 | `apt`、`dnf`、`yum` |
| Repository / Repo | 软件仓库 | 提供可安装软件包的源 | 不同发行版和版本不能随意混用 |
| DKMS | Dynamic Kernel Module Support | 内核升级时自动重新编译第三方内核模块 | NIC/GPU 驱动经常依赖它 |
| Initramfs | Initial RAM Filesystem | 内核早期启动时使用的临时根文件系统 | 常包含磁盘或网卡启动驱动 |
| udev | - | Linux 的设备发现与设备节点管理机制 | 可按 MAC、PCI 地址创建稳定规则 |
| sysctl | - | 调整运行中内核参数的接口 | 常用于网络缓冲区、转发和内存参数 |
| SSH | Secure Shell | 远程登录和安全命令执行协议 | 基础设施主机最常见的管理方式 |
| Bastion Host | 堡垒机 / 跳板机 | 进入内网主机的受控入口 | 便于权限控制和审计 |

---

## 内存与性能

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| Cache | 高速缓存 | 位于 CPU 与 DRAM 之间的小而快的存储 | L1/L2/L3 越靠近核心越快、越小 |
| Cache Line | 缓存行 | Cache 与内存交换数据的最小粒度 | 现代 CPU 常见为 64 B |
| Cache Miss | 缓存未命中 | 所需数据不在当前缓存层，需要向下一级取 | 会带来较高延迟 |
| Cache Coherence | 缓存一致性 | 多核缓存对同一数据保持一致的机制 | 共享写热点会降低扩展性 |
| False Sharing | 伪共享 | 不同线程写同一缓存行中的不同变量却互相失效 | 可通过填充或分片避免 |
| DRAM | Dynamic Random-Access Memory | 动态随机存取内存，即常说的内存条 | 断电后数据丢失，需要刷新 |
| SRAM | Static Random-Access Memory | 静态随机存取内存，快但昂贵 | 常用于 CPU Cache |
| HBM | High Bandwidth Memory | 高带宽堆叠内存 | 常见于高端 GPU/加速器 |
| Huge Page | 大页 | 比普通 4 KiB 页更大的内存页 | DPDK 常使用 2 MiB 或 1 GiB 页 |
| TLB | Translation Lookaside Buffer | 虚拟地址到物理地址转换的缓存 | 大页可降低 TLB miss |
| Page Fault | 缺页异常 | 访问的虚拟内存页尚未映射或不在内存中 | 严重时会引发磁盘换页 |
| Swap | 交换空间 | 内存不足时暂存到磁盘的区域 | 对低延迟服务通常应谨慎使用 |
| OOM | Out Of Memory | 内存耗尽事件 | Linux OOM Killer 可能终止某个进程 |
| Bandwidth | 带宽 | 单位时间可传输的数据量 | 常用 GB/s、Gb/s |
| Latency | 延迟 | 单个请求从开始到完成所需时间 | 关注 p50、p95、p99，而非只有平均值 |
| Throughput | 吞吐量 | 单位时间完成的请求数或数据量 | 受 CPU、I/O、并发和背压共同限制 |
| IOPS | I/O Operations Per Second | 每秒 I/O 操作次数 | 小块随机存储 I/O 常用指标 |
| QPS / RPS | Queries / Requests Per Second | 每秒查询/请求数 | 用于服务端吞吐指标 |
| Tail Latency | 长尾延迟 | 高分位（如 p99）延迟 | 往往比平均延迟更影响用户体验 |
| Jitter | 抖动 | 延迟随时间的波动 | 实时、网络与 benchmark 特别关注 |
| Benchmark | 基准测试 | 用标准工作负载衡量性能 | 必须记录版本、配置、数据和拓扑 |

---

## 硬件、总线与固件

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| SoC | System on Chip | 将 CPU、内存控制器、I/O 等集成在一颗芯片中的系统 | DPU 通常包含 Arm SoC |
| NIC | Network Interface Card | 网卡 | 可为普通 NIC、SmartNIC 或 DPU |
| HCA | Host Channel Adapter | RDMA/InfiniBand 语境中的网络适配器 | Linux 中常以 `mlx5_*` 出现 |
| PCIe | Peripheral Component Interconnect Express | CPU 与 GPU、NIC、NVMe 等设备的高速串行总线 | 常写成 Gen5 x16 等 |
| Lane | 通道 | PCIe 中的一对收发差分信号通路 | x16 表示 16 条 lane |
| Root Complex | 根复合体 | CPU/芯片组连接 PCIe 设备的根端 | 影响 GPU/NIC 的拓扑和 NUMA 距离 |
| PCIe Switch | PCIe 交换芯片 | 将一个上游 PCIe 连接扩展为多个下游设备 | 可能影响带宽共享与 P2P |
| P2P | Peer-to-Peer | 两个 PCIe 设备直接传输数据 | GPU Direct、NVMe/DPU 常讨论它 |
| BAR | Base Address Register | PCIe 设备暴露给 CPU 的 MMIO 地址窗口 | 大 BAR 可能需要 BIOS 配置 |
| MMIO | Memory-Mapped I/O | 将设备寄存器映射到 CPU 地址空间访问 | CPU 通过读写地址控制设备 |
| BIOS / UEFI | Basic I/O System / Unified Extensible Firmware Interface | 服务器启动与硬件初始化固件 | 设置 SR-IOV、IOMMU、启动顺序等 |
| BMC | Baseboard Management Controller | 独立于主机 OS 的带外管理控制器 | IPMI、Redfish、远程 KVM 常由它提供 |
| OOB | Out-of-Band | 带外管理网络 | 主机宕机时仍可通过 BMC 管理 |
| IPMI | Intelligent Platform Management Interface | 传统服务器带外管理标准 | 可查看传感器、开关机、串口控制台 |
| Redfish | - | 基于 HTTPS/REST 的现代服务器管理标准 | 常作为 IPMI 的补充或替代 |
| Firmware | 固件 | 运行在网卡、SSD、BMC 等设备中的底层软件 | 升级需匹配硬件型号与版本矩阵 |
| Driver | 驱动程序 | 使操作系统使用硬件设备的软件 | 内核态驱动与用户态库常需配套 |
| RShim | Remote Shim | BlueField 主机与 Arm 侧之间的管理/控制通道 | 可用于刷 BFB、串口和恢复 |

---

## 网络基础

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| L2 / L3 / L4 | Layer 2 / 3 / 4 | OSI 中的数据链路、网络、传输层 | 分别常对应 MAC、IP、TCP/UDP |
| Ethernet | 以太网 | 最常用的局域网技术 | 速率常见 1/10/25/100/200/400GbE |
| MAC Address | Media Access Control Address | 网卡在二层网络中的硬件地址 | 交换机依据它转发帧 |
| VLAN | Virtual Local Area Network | 在同一物理网络中划分逻辑二层网络 | 802.1Q VLAN ID 范围为 1–4094 |
| VXLAN | Virtual Extensible LAN | 将二层报文封装在三层 UDP 网络中的 overlay 技术 | 云和 Kubernetes CNI 常用 |
| Geneve | Generic Network Virtualization Encapsulation | 可扩展的网络虚拟化封装协议 | 常用于云网络和 OVS |
| MTU | Maximum Transmission Unit | 单个二层帧承载的最大 IP 包大小 | Jumbo Frame 常设为 9000，链路两端须一致 |
| Jumbo Frame | - | 大于默认 1500 字节的以太网帧 | 可降低高吞吐场景的包处理开销 |
| IP | Internet Protocol | 网络层寻址与路由协议 | IPv4 和 IPv6 |
| CIDR | Classless Inter-Domain Routing | 用前缀长度表示网段的方法 | 例如 `10.0.0.0/24` |
| Gateway | 网关 | 将流量转发到其他网络的下一跳 | 默认路由通常指向默认网关 |
| ARP | Address Resolution Protocol | IPv4 中将 IP 解析为 MAC 的协议 | IPv6 对应 NDP |
| NDP | Neighbor Discovery Protocol | IPv6 的邻居发现与地址解析机制 | 基于 ICMPv6 |
| DNS | Domain Name System | 将域名解析为 IP 地址的系统 | 排查时应区分 DNS 与网络连通性问题 |
| DHCP | Dynamic Host Configuration Protocol | 自动分配 IP、网关、DNS 等网络配置 | 静态地址与 DHCP 需避免冲突 |
| TCP | Transmission Control Protocol | 面向连接、可靠、有序的传输协议 | 有拥塞控制与重传 |
| UDP | User Datagram Protocol | 无连接的数据报传输协议 | 低开销，但可靠性需由应用处理 |
| QUIC | Quick UDP Internet Connections | 构建在 UDP 上的可靠加密传输协议 | HTTP/3 使用 QUIC |
| TLS | Transport Layer Security | 传输层加密和身份认证协议 | HTTPS 即 HTTP over TLS |
| HTTP / HTTPS | Hypertext Transfer Protocol / Secure | 常见应用层请求协议 / 其 TLS 加密形式 | API、对象存储和 Web 服务常用 |
| Load Balancer / LB | 负载均衡器 | 将请求分配给多个后端实例 | 可工作在 L4 或 L7 |
| L4 LB | 四层负载均衡 | 基于 IP、端口、TCP/UDP 转发 | 性能高、不了解 HTTP 语义 |
| L7 LB | 七层负载均衡 | 可基于 HTTP 路径、Host、Header 路由 | Ingress、API Gateway 常属此类 |
| NAT | Network Address Translation | 修改报文中的地址或端口 | SNAT 出网，DNAT/端口映射入站 |
| SNAT / DNAT | Source / Destination NAT | 改写源地址 / 目的地址 | Kubernetes 网络排障常见 |
| Firewall | 防火墙 | 按规则允许、拒绝或记录网络流量 | 可在主机、网络设备或云上 |
| ACL | Access Control List | 访问控制规则集合 | 可用于网络、文件或对象权限 |
| Proxy | 代理 | 代替客户端或服务端转发请求的组件 | 分正向代理和反向代理 |
| Reverse Proxy | 反向代理 | 位于服务端前方，接收外部请求再转发给后端 | Nginx、Envoy 常见用途 |
| eBPF | extended Berkeley Packet Filter | 在受控环境运行的小程序机制 | 用于观测、网络、流量控制和安全 |

---

## RDMA、DPU 与网络卸载

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| RDMA | Remote Direct Memory Access | 允许网卡在网络两端直接访问已注册内存的技术 | 降低 CPU 拷贝和协议栈开销 |
| InfiniBand / IB | - | 面向高性能计算的低延迟网络互连 | RDMA 的原生传输网络 |
| RoCE | RDMA over Converged Ethernet | 在以太网上运行 RDMA | RoCEv2 使用 UDP/IP，可跨三层网络 |
| PFC | Priority Flow Control | 按优先级暂停以太网流量的机制 | RoCE 无损网络中常见；配置不当会扩散拥塞 |
| ECN | Explicit Congestion Notification | 显式标记网络拥塞而不是直接丢包 | 与 DCQCN 等拥塞控制协同 |
| DCQCN | Data Center Quantized Congestion Notification | RoCE 常见的数据中心拥塞控制算法 | 需 NIC、交换机与主机配套配置 |
| QP | Queue Pair | RDMA 发送队列和接收队列的逻辑对 | RDMA 通信的核心对象 |
| CQ | Completion Queue | RDMA 操作完成事件队列 | 轮询 CQ 是常见高性能模式 |
| MR | Memory Region | 注册给 RDMA 网卡访问的内存区 | 会获得 lkey/rkey 等访问凭据 |
| rkey / lkey | Remote / Local Key | RDMA 内存访问权限密钥 | 用于保护 MR 的本地或远程访问 |
| Verbs | - | RDMA 的底层编程模型/API 家族 | `ibverbs` 是常见 Linux 用户态接口 |
| GPUDirect RDMA | - | NIC 与 GPU 内存间直接 DMA 的能力 | 拓扑、驱动和版本必须兼容 |
| DPU | Data Processing Unit | 将可编程计算、网络和安全/存储卸载整合到一张卡的设备 | BlueField 属于 DPU |
| SmartNIC | 智能网卡 | 带可编程处理能力的网卡 | 有些产品的 Arm 侧能力与 DPU 不同 |
| BlueField | - | NVIDIA 的 DPU 产品系列 | 具有 Arm、网络加速和可编程数据路径能力 |
| ECPF | Embedded CPU Function | BlueField 中由嵌入式 Arm 侧拥有和控制 NIC 资源的模式 | 即 DPU Mode；适合在 DPU 上部署程序 |
| NIC Mode | - | 将 BlueField 表现为普通网卡的模式 | Arm OS/服务不可用于 DPU 上的算子执行 |
| eSwitch | Embedded Switch | NIC/DPU 内置的虚拟交换机 | 可将规则卸载到硬件转发路径 |
| Representor | - | 代表 VF、PF 或端口的 Linux 网络接口 | OVS/TC 用它管理 eSwitch 流量 |
| SR-IOV | Single Root I/O Virtualization | 一张物理 PCIe 设备创建多个虚拟功能 | PF 管理，VF 分配给 VM/容器 |
| PF / VF | Physical / Virtual Function | SR-IOV 的物理功能 / 虚拟功能 | VF 性能接近直通，但功能受限 |
| DOCA | NVIDIA Data Center on a Chip Architecture | NVIDIA 的 BlueField/网络加速软件框架和 SDK | 主机与 DPU 侧版本应配套 |
| DPA | Data Path Accelerator | BF3 上面向网络和 I/O 数据路径的可编程加速子系统 | 并非通用 CUDA/GPU 计算单元 |
| DPDK | Data Plane Development Kit | 用户态高速报文处理框架 | 常配合 hugepage、轮询和 CPU 绑核 |
| VPP | Vector Packet Processing | 高性能用户态网络数据平面框架 | 使用向量化报文处理 |
| OVS | Open vSwitch | 软件虚拟交换机 | 常用于虚拟化、容器和 DPU eSwitch 卸载 |
| TC | Traffic Control | Linux 内核流量控制框架 | 可管理 qdisc、filter 和硬件 offload |
| XDP | eXpress Data Path | 在网卡驱动早期处理报文的 eBPF 执行路径 | 适合低开销过滤、转发和采样 |

---

## 存储

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| Block Storage | 块存储 | 将存储暴露为可读写的数据块设备 | 云盘、SAN、NVMe SSD 常属此类 |
| File Storage | 文件存储 | 通过目录、文件和权限提供共享存储 | NFS、SMB 是常见协议 |
| Object Storage | 对象存储 | 以对象、元数据和 key 管理数据 | S3 是最常见接口之一 |
| HDD | Hard Disk Drive | 机械硬盘 | 容量大但随机 I/O 延迟较高 |
| SSD | Solid State Drive | 固态硬盘 | 常见 SATA SSD、NVMe SSD |
| NVMe | Non-Volatile Memory express | 面向 PCIe SSD 的高性能访问协议 | 也可通过网络使用 NVMe-oF |
| NVMe-oF | NVMe over Fabrics | 将 NVMe 命令经 RDMA/TCP/FC 等网络传输 | 用于远程高性能块存储 |
| SATA / SAS | Serial ATA / Serial Attached SCSI | 传统磁盘连接接口/协议 | NVMe 通常性能更高 |
| RAID | Redundant Array of Independent Disks | 将多块盘组合以获得冗余或性能 | RAID 不等于备份 |
| JBOD | Just a Bunch Of Disks | 多块独立磁盘，不做 RAID 聚合 | 分布式存储常自行做副本/纠删码 |
| LVM | Logical Volume Manager | Linux 的逻辑卷管理层 | 可扩容、快照和管理卷组 |
| Filesystem | 文件系统 | 组织文件、目录和元数据的格式/软件层 | ext4、XFS、btrfs |
| inode | Index Node | Unix 文件系统中描述文件元数据的结构 | inode 耗尽也会导致不能创建文件 |
| Mount | 挂载 | 将文件系统接入目录树的操作 | 容器的 volume 也依赖挂载 |
| NFS | Network File System | 常见的网络文件系统协议 | Kubernetes RWX 卷常用 |
| Ceph | - | 分布式存储系统，可提供块、文件和对象存储 | RBD、CephFS、RGW 对应不同接口 |
| Replication | 副本 | 将数据保存多份以提升可用性 | 影响容量、写延迟和一致性 |
| Erasure Coding / EC | 纠删码 | 用数据块和校验块容忍磁盘故障 | 比多副本省空间，但计算/修复开销更高 |
| Snapshot | 快照 | 某时刻数据状态的逻辑副本 | 通常不能替代跨域备份 |
| Backup | 备份 | 为恢复而保留的独立数据副本 | 应定期验证可恢复性 |
| RPO | Recovery Point Objective | 可接受的数据丢失时间窗口 | 例如 RPO 5 分钟 |
| RTO | Recovery Time Objective | 可接受的服务恢复时间 | 灾备方案的重要目标 |

---

## 虚拟化与容器

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| Hypervisor | 虚拟机监控器 | 让一台物理机运行多个虚拟机的软件层 | KVM、ESXi、Hyper-V |
| VM | Virtual Machine | 模拟出完整硬件与 OS 的隔离运行环境 | 隔离较强，资源开销较容器大 |
| KVM | Kernel-based Virtual Machine | Linux 内核中的硬件虚拟化能力 | 常配合 QEMU 管理 VM |
| QEMU | Quick Emulator | 模拟器和虚拟机运行工具 | KVM 加速时常承担设备模拟 |
| VirtIO | - | 虚拟机与宿主机之间的半虚拟化设备标准 | 网络和块存储设备最常见 |
| Passthrough | 设备直通 | 将物理设备直接分配给虚拟机 | 需要 IOMMU，常用于 GPU/NIC |
| Container | 容器 | 使用 namespace/cgroup 隔离的进程封装 | 与宿主机共享内核 |
| OCI | Open Container Initiative | 容器镜像与运行时规范 | Docker 镜像通常符合 OCI 规范 |
| Image | 容器镜像 | 运行容器所需文件系统和元数据模板 | 不应包含密钥或运行时数据 |
| Registry | 镜像仓库 | 存放、分发容器镜像的服务 | Docker Hub、Harbor、ECR 等 |
| Runtime | 容器运行时 | 创建并运行容器的组件 | containerd、CRI-O、runc |
| Docker | - | 流行的容器构建和运行工具链 | K8s 中通常由 containerd 实际运行容器 |
| Volume | 数据卷 | 独立于容器可写层的持久化数据挂载 | 删除容器不应误删重要数据 |
| OverlayFS | - | 联合文件系统，将多层目录叠加为一个视图 | 容器镜像层常用 |

---

## Kubernetes 与云原生

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| Kubernetes / K8s | - | 编排容器应用的集群系统 | 负责调度、服务发现、扩缩容和自愈 |
| Control Plane | 控制平面 | 维护集群期望状态并作出调度决策的组件集合 | 包括 API Server、Scheduler 等 |
| Data Plane | 数据平面 | 实际承载业务流量或执行数据操作的部分 | 与控制平面相对 |
| Node | 节点 | Kubernetes 集群中的一台工作机或控制机 | 可为物理机或 VM |
| Pod | - | K8s 最小调度单位，可包含一个或多个容器 | 同一 Pod 通常共享网络命名空间 |
| Deployment | - | 声明式管理无状态 Pod 副本与滚动升级 | 典型 Web/API 服务使用 |
| StatefulSet | - | 管理有稳定身份和存储需求的 Pod | 数据库、消息队列常使用 |
| DaemonSet | - | 确保每个（或指定）节点运行一个 Pod | 日志、CNI、监控 agent 常用 |
| Job / CronJob | - | 一次性任务 / 定时任务 | 批处理、迁移、备份常用 |
| Service | - | 为一组 Pod 提供稳定访问入口的抽象 | ClusterIP、NodePort、LoadBalancer |
| Ingress | - | 将外部 HTTP(S) 路由到集群 Service 的 API 对象 | 需配合 Ingress Controller |
| Gateway API | - | 新一代 K8s 流量管理 API | 比 Ingress 更可表达复杂路由 |
| CNI | Container Network Interface | 为 Pod 配置网络的插件规范 | Calico、Cilium、Flannel |
| CSI | Container Storage Interface | 为 K8s 提供存储卷的插件规范 | 云盘、Ceph、NFS 均可实现 |
| CRI | Container Runtime Interface | kubelet 与容器运行时通信的接口 | containerd、CRI-O 实现它 |
| CRD | Custom Resource Definition | 将自定义资源类型注册到 K8s API | Operator 常通过 CRD 管理应用 |
| Operator | - | 用控制器将应用运维知识编码进 K8s 的模式 | 不等于普通运维人员 |
| Helm | - | Kubernetes 包管理和模板工具 | Chart 是其应用包格式 |
| Kustomize | - | 基于 patch/overlay 管理 K8s YAML 的工具 | 常与 GitOps 一起使用 |
| HPA | Horizontal Pod Autoscaler | 按 CPU、内存或自定义指标横向扩缩 Pod | 不直接改变单 Pod 资源 |
| VPA | Vertical Pod Autoscaler | 调整 Pod 的 CPU/内存 requests/limits | 可能需要重建 Pod |
| PDB | Pod Disruption Budget | 限制主动中断时可同时不可用的 Pod 数 | 维护升级时很重要 |
| Request / Limit | 资源请求 / 上限 | 调度所需资源 / 容器可使用的最大资源 | CPU limit 可能导致 throttling |

---

## 分布式系统与可靠性

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| HA | High Availability | 高可用；通过冗余减少单点故障 | 常以可用性百分比衡量 |
| SPOF | Single Point Of Failure | 单点故障 | 任一组件故障即可导致服务不可用 |
| Fault Domain | 故障域 | 可能一起故障的一组资源边界 | 如同一机架、可用区、地域 |
| AZ | Availability Zone | 同一区域内相对独立的故障域 | 云厂商概念，具体定义不同 |
| Region | 地域 | 云资源部署的大地理区域 | 跨 Region 延迟和成本更高 |
| Cluster | 集群 | 多台协作提供服务的机器集合 | 需明确控制面和数据面边界 |
| Sharding | 分片 | 将数据或请求按规则拆分到多个节点 | 水平扩展常见手段 |
| Partition | 分区 | 数据集被拆开的一个逻辑部分 | 在不同系统中与 shard 含义接近 |
| Leader / Follower | 主 / 从（跟随者） | 一个节点负责写入协调，其他节点复制或服务读取 | 也称 primary/replica |
| Quorum | 法定多数 | 达到足够多节点同意才确认操作 | 通常与多数派共识有关 |
| Consensus | 共识 | 多节点对顺序或状态达成一致 | Raft、Paxos 是典型算法 |
| Raft | - | 易理解的分布式共识算法 | etcd 常使用 |
| CAP Theorem | CAP 定理 | 网络分区出现时，一致性和可用性不能同时完全满足 | 不是日常架构的简单三选一 |
| Consistency | 一致性 | 副本读取和写入所遵循的数据正确性语义 | 需说明强一致、最终一致等 |
| Eventual Consistency | 最终一致性 | 允许短时间副本不一致，最终会收敛 | 常见于高可用分布式存储 |
| Idempotency | 幂等性 | 同一请求重复执行，结果与执行一次相同 | 重试、支付、消息消费很重要 |
| Backpressure | 背压 | 下游处理不过来时向上游施加限速 | 避免队列无限增长和雪崩 |
| Rate Limiting | 限流 | 限制单位时间内允许的请求量 | 保护服务和公平分配资源 |
| Circuit Breaker | 熔断 | 下游持续失败时快速失败，避免继续压垮它 | 常配合超时、重试和降级 |
| Retry | 重试 | 请求失败后再次尝试 | 必须限制次数并使用退避 |
| Exponential Backoff | 指数退避 | 每次重试逐步增加等待时间 | 通常加入随机抖动避免同步重试 |
| SLI | Service Level Indicator | 服务质量的测量指标 | 如成功率、延迟、可用性 |
| SLO | Service Level Objective | SLI 的目标值 | 如 30 天内 99.9% 请求成功 |
| SLA | Service Level Agreement | 面向客户的服务等级承诺 | 常包含违约责任 |

---

## 可观测性与性能分析

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| Observability | 可观测性 | 从系统输出推断内部状态和原因的能力 | 通常由指标、日志、追踪支撑 |
| Metrics | 指标 | 可聚合的数值时间序列 | CPU 使用率、QPS、p99 延迟 |
| Logs | 日志 | 带上下文的离散事件记录 | 应使用结构化日志并避免泄露敏感数据 |
| Traces | 链路追踪 | 一个请求跨服务的调用路径和耗时记录 | 通过 trace ID 关联 |
| Profile | 性能剖析 | 采样或统计程序的 CPU、内存、锁等开销 | 用来定位热点，不等于监控 |
| APM | Application Performance Monitoring | 应用性能监控 | 常集成指标、trace、错误分析 |
| RUM | Real User Monitoring | 真实用户监控 | 从浏览器或客户端采集体验指标 |
| Synthetic Monitoring | 拨测 | 用模拟请求持续探测服务可用性 | 适合发现外部访问故障 |
| Prometheus | - | 拉取式指标采集、存储和告警系统 | Kubernetes 生态常用 |
| OpenTelemetry / OTel | - | 统一采集 metrics、logs、traces 的开放标准 | 便于避免厂商锁定 |
| Grafana | - | 可视化指标、日志和追踪的仪表盘工具 | 通常连接 Prometheus/Loki/Tempo 等 |
| Alert | 告警 | 指标触发的需要关注事件 | 应基于症状和影响，而非每个资源波动 |
| Alert Fatigue | 告警疲劳 | 低质量或过多告警导致人员忽略真正问题 | 需定期清理无行动价值的告警 |
| Runbook | 操作手册 | 告警或故障的标准排查、处置步骤 | 应随系统演进维护 |
| SRE | Site Reliability Engineering | 用软件工程方法做可靠性运维的实践 | 强调 SLO、自动化与错误预算 |
| Error Budget | 错误预算 | 在 SLO 下允许消耗的不可用额度 | 影响发布速度与稳定性取舍 |
| Flame Graph | 火焰图 | 用调用栈宽度展示热点开销的图 | 宽度通常代表采样次数或耗时 |
| `perf` | - | Linux 性能分析工具 | 可分析 CPU 事件、调用栈、缓存 miss |
| eBPF Tracing | eBPF 追踪 | 利用 eBPF 动态观测内核与应用事件 | bpftrace、BCC、Pixie 等会使用 |

---

## 交付、自动化与配置管理

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| Git | - | 分布式版本控制系统 | commit 应可追溯地对应代码状态 |
| CI | Continuous Integration | 持续集成；每次变更自动构建、检查和测试 | GitHub Actions、GitLab CI 等 |
| CD | Continuous Delivery / Deployment | 持续交付 / 持续部署 | 前者通常仍需人工批准，后者自动上线 |
| Pipeline | 流水线 | 一串自动化构建、测试、发布步骤 | 应可重复且有明确输入输出 |
| Artifact | 构建产物 | 构建后可部署或可复用的结果 | 如 wheel、镜像、二进制、报告 |
| IaC | Infrastructure as Code | 用代码定义和变更基础设施 | 使环境可审查、可复现 |
| Terraform | - | 声明式基础设施编排工具 | 使用 state 记录已管理资源 |
| State | 状态文件 | IaC 工具记录真实资源映射的文件 | 应远程保存、加密并控制并发 |
| Ansible | - | 基于 SSH/agentless 的配置自动化工具 | 常用于装包、配置和批量运维 |
| Playbook | - | Ansible 的自动化任务定义文件 | 应保持幂等 |
| GitOps | - | 将 Git 作为期望部署状态的来源并自动同步 | Argo CD、Flux 是常见工具 |
| Immutable Infrastructure | 不可变基础设施 | 不在原机器上手改，而是构建新镜像或实例替换 | 降低配置漂移 |
| Configuration Drift | 配置漂移 | 实际环境逐渐偏离声明配置 | 手工登录修改是常见来源 |
| Canary Release | 金丝雀发布 | 先向少量流量或实例发布新版本 | 观察指标后逐步扩大 |
| Blue-Green Deployment | 蓝绿发布 | 维护两套环境，在其间切换流量 | 回滚快，但资源开销较高 |
| Feature Flag | 功能开关 | 不重新部署即可控制功能是否启用 | 应管理过期 flag |
| Rollback | 回滚 | 发布失败时恢复到已知稳定版本 | 需要兼顾数据库兼容性 |
| Secret | 密钥 / 凭据 | 密码、Token、私钥等敏感配置 | 不应写入 Git、镜像或普通日志 |

---

## 安全

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| IAM | Identity and Access Management | 身份认证、授权和权限管理体系 | 云平台和 K8s 的基础能力 |
| Authentication / AuthN | 身份认证 | 确认“你是谁” | 密码、证书、OIDC 等 |
| Authorization / AuthZ | 授权 | 确认“你能做什么” | RBAC、ACL、策略引擎 |
| RBAC | Role-Based Access Control | 基于角色授予权限的模型 | K8s 常用授权机制 |
| OIDC | OpenID Connect | 建立在 OAuth 2.0 上的身份层协议 | 常用于单点登录 |
| OAuth 2.0 | - | 委托授权框架 | 解决授权，不等同于用户认证本身 |
| mTLS | Mutual TLS | 客户端和服务端相互校验证书的 TLS | 服务网格常使用 |
| PKI | Public Key Infrastructure | 证书、密钥、CA 和签发/吊销体系 | mTLS 的基础 |
| CA | Certificate Authority | 签发和信任数字证书的机构或服务 | 可是公有 CA 或内部 CA |
| KMS | Key Management Service | 管理、轮换和使用加密密钥的服务 | 云 KMS、HSM 常配合使用 |
| HSM | Hardware Security Module | 保护密钥并执行加密操作的专用硬件 | 私钥可不离开硬件 |
| Encryption at Rest | 静态加密 | 数据落盘或存储时加密 | 还需管理密钥和备份 |
| Encryption in Transit | 传输加密 | 数据在网络中传输时加密 | 常用 TLS/mTLS |
| CVE | Common Vulnerabilities and Exposures | 公开漏洞的标准编号 | 例如 CVE-YYYY-NNNN |
| CVSS | Common Vulnerability Scoring System | 漏洞严重性评分体系 | 分数应结合真实暴露面判断 |
| SBOM | Software Bill of Materials | 软件组件清单 | 用于供应链审计和漏洞响应 |
| Zero Trust | 零信任 | 不因网络位置默认信任任何访问者 | 强调持续验证与最小权限 |

---

## AI 与加速计算

| 缩写/名词 | 全称 | 通俗释义 | 备注 |
|---|---|---|---|
| GPU | Graphics Processing Unit | 大规模并行计算加速器 | AI 训练和推理的主力 |
| NPU | Neural Processing Unit | 专门执行神经网络计算的加速器 | 常见于移动端和边缘设备 |
| TPU | Tensor Processing Unit | Google 的张量计算加速器系列 | 面向矩阵或张量运算 |
| FPGA | Field-Programmable Gate Array | 可通过逻辑配置实现专用数据路径的芯片 | 灵活但开发周期较长 |
| CUDA | Compute Unified Device Architecture | NVIDIA GPU 的编程平台和生态 | CUDA 代码不能直接在 DPU Arm/DPA 上执行 |
| ROCm | Radeon Open Compute | AMD GPU 的开源计算软件栈 | 对应 CUDA 的生态定位 |
| Tensor Core | - | GPU 中专门加速矩阵乘累加的计算单元 | 常用于低精度 AI 运算 |
| FLOPS | Floating-Point Operations Per Second | 每秒浮点运算次数 | 不代表端到端模型吞吐 |
| TOPS | Tera Operations Per Second | 每秒万亿次运算 | NPU/INT8 推理宣传中常见 |
| FP32 / FP16 / BF16 | Floating Point 32 / 16 / Brain Floating Point 16 | 常用浮点数格式 | 精度、显存占用和吞吐存在取舍 |
| INT8 / INT4 | Integer 8 / 4-bit | 低比特整数计算格式 | 常用于量化推理 |
| Quantization | 量化 | 用更低精度表示权重或激活以节省资源 | 需要验证精度损失 |
| Inference | 推理 | 用训练好的模型处理新输入 | 常更重视延迟和成本 |
| Training | 训练 | 用数据更新模型参数的过程 | 通常需要反向传播和更高算力 |
| Batch Size | 批大小 | 一次送入计算的样本数 | 影响吞吐、显存和延迟 |
| Operator / Op | 算子 | 模型或数据处理流程中的基本操作 | 如 matmul、softmax、filter |
| Kernel | 计算内核 | 被编译并在特定设备执行的核心函数 | CUDA kernel、DPA kernel 含义依上下文不同 |
| PNM | Processing Near Memory | 近存计算：让计算靠近数据所在内存，减少数据搬运 | 研究中需单独定义硬件模型与测量边界 |

---

## 使用约定

1. 术语首次出现时，优先写“中文（英文，缩写）”，后续使用缩写。
2. 同一术语在不同上下文含义可能不同；例如 data plane 在网络、Kubernetes 和存储中都有使用，请同时记录上下文。
3. 性能结论必须附带测试环境：硬件型号、固件/驱动版本、OS/内核、拓扑、工作负载、并发、数据规模和指标分位数。
4. 新增条目时沿用四列表格：`缩写/名词 | 全称 | 通俗释义 | 备注`；不确定的厂商实现或版本限制应在备注中标明。
