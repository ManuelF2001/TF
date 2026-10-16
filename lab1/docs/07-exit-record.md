# Exit record (four lines)

1. **Claim considered:** strategy D (primary for everything) is linearizable
   under crashes, delays and partitions, and available exactly to the
   clients whose server can reach n0.
2. **Strongest evidence:** 19 Maelstrom runs, all valid, including n0
   crashes (0 ok afterwards) and partitions where n0 executed a write whose
   reply was lost and another client read it — the checker still found a
   linearization (`runs/p4-partition-2`).
3. **Limitation / unresolved question:** there is no failover, and the
   backups' copies silently diverge (`runs/p4-partition`: n2 = 4, n0 = 3),
   so no backup could safely take over; we cannot test n0 losing its memory.
4. **Next action:** make a backup able to take over safely — n0 replies
   only after a majority has the update, ordered updates, and agreement on
   who the primary is — then test with `MS_CRASH="n0@5"` and partitions.
