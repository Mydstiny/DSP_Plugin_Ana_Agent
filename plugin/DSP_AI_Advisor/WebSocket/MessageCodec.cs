using System;
using Newtonsoft.Json;

namespace DSP_AI_Advisor.WebSocket
{
    /// <summary>
    /// WebSocket 消息信封编解码 — 遵循 shared/protocol.md v0.1.0.
    /// </summary>
    public static class MessageCodec
    {
        /// <summary>
        /// 封装为协议信封: { channel, type, payload, id, timestamp }
        /// </summary>
        public static string Encode(string channel, string type, object payload)
        {
            var envelope = new
            {
                channel,
                type,
                payload,
                id = Guid.NewGuid().ToString(),
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
            };

            return JsonConvert.SerializeObject(envelope, Formatting.None);
        }

        /// <summary>
        /// 便捷方法 — 编码 SnapshotData 为 snapshot channel 消息.
        /// </summary>
        public static string EncodeSnapshot(Models.SnapshotData data)
        {
            return Encode("snapshot", "periodic_snapshot", data);
        }

        /// <summary>
        /// 解码消息信封, 提取 channel/type/payload.
        /// 返回 null 表示解析失败.
        /// </summary>
        public static MessageEnvelope Decode(string rawJson)
        {
            try
            {
                return JsonConvert.DeserializeObject<MessageEnvelope>(rawJson);
            }
            catch (Exception)
            {
                return null;
            }
        }
    }

    [Serializable]
    public class MessageEnvelope
    {
        [JsonProperty("channel")]
        public string Channel { get; set; }

        [JsonProperty("type")]
        public string Type { get; set; }

        [JsonProperty("payload")]
        public string Payload { get; set; }  // raw JSON string

        [JsonProperty("id")]
        public string Id { get; set; }

        [JsonProperty("timestamp")]
        public long Timestamp { get; set; }
    }
}
