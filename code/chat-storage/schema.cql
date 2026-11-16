-- Chapter 01: message storage keyed for the access pattern, not for the entity model.
-- Run with: cqlsh -f code/chat-storage/schema.cql

CREATE KEYSPACE IF NOT EXISTS chat
  WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': 3};

-- bucket = a static time window (epoch_day / 10). Putting it in the partition key
-- bounds partition size so compaction and reads stay predictable.
CREATE TABLE IF NOT EXISTS chat.messages (
    channel_id  bigint,
    bucket      int,
    message_id  bigint,          -- Snowflake: chronologically sortable
    author_id   bigint,
    content     text,
    edited_at   timestamp,
    PRIMARY KEY ((channel_id, bucket), message_id)
) WITH CLUSTERING ORDER BY (message_id DESC)
  AND compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_size': 1,
    'compaction_window_unit': 'DAYS'
  }
  AND default_time_to_live = 0;

-- Small side table for channel metadata: read constantly, written rarely.
CREATE TABLE IF NOT EXISTS chat.channels (
    channel_id  bigint PRIMARY KEY,
    guild_id    bigint,
    name        text,
    updated_at  timestamp
);
