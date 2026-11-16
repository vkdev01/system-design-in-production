# Chapter 14 - news feed and timeline

```bash
cd code/feed
python bench.py
```

```
push-everything : 200,147,000 timeline writes/s
hybrid          :     147,020 timeline writes/s   (1,361x less)
pull-everything :  48,000,000 list reads/s
full timelines  :       4,800 GB of Redis
head only (40)  :         240 GB of Redis   (20x less)
```

- `timeline.py` - Redis ZSET semantics in memory (head-capped) plus a bounded
  k-way merge.
- `fanout.py` - the push/pull tier decision and a reader that caps its merge at
  8 celebrity sources.
- `bench.py` - the three strategies on the chapter's follower distribution.
