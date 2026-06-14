# W5 vm-guest victim-delta — superseded

The vm-guest W5 colocation leg is now reported in
[w5-victim-delta.md](w5-victim-delta.md) alongside bare and container, all run at
the unified 1/3 footprint (16 vCPU / 83 GiB per instance, hard CPU pinning,
correct 281600 MB/s mbw ceiling) on 2026-06-14.

This file previously held a separate vm-guest table because the earlier run sized
each co-located KVM guest at 96 GiB (so two fit in host RAM), giving it a
different solo baseline that could not be merged with the bare/container table.
The 2026-06-14 W5 run removes that mismatch — victim and aggressor VMs each take
one host third — so the separate report is retired. The portable signals
(membw_est, schedlat) behave consistently across all three environments; see the
unified report.
