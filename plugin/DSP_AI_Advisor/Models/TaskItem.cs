using System;
using System.Collections.Generic;
using Newtonsoft.Json;

namespace DSP_AI_Advisor.Models
{
    /// <summary>
    /// C# task item — field names match Python TaskItem.model_dump_json() output.
    /// Received from Companion via WebSocket task_list_update messages.
    /// </summary>
    [Serializable]
    public class TaskItem
    {
        [JsonProperty("id")]
        public string Id { get; set; }

        [JsonProperty("priority")]
        public string Priority { get; set; }  // "critical" | "high" | "medium" | "low"

        [JsonProperty("category")]
        public string Category { get; set; }   // "power" | "production" | "logistics" | "upgrade"

        [JsonProperty("title")]
        public string Title { get; set; }

        [JsonProperty("description")]
        public string Description { get; set; }

        [JsonProperty("suggested_action")]
        public string SuggestedAction { get; set; }

        [JsonProperty("planet")]
        public string Planet { get; set; }

        [JsonProperty("planet_id")]
        public int? PlanetId { get; set; }

        [JsonProperty("estimated_effort")]
        public string EstimatedEffort { get; set; }

        [JsonProperty("status")]
        public string Status { get; set; }  // "new" | "tracked" | "resolved" | "dismissed"

        /// <summary>
        /// Whether this task is actionable (not resolved or dismissed).
        /// </summary>
        [JsonIgnore]
        public bool IsActive =>
            Status == "new" || Status == "tracked";
    }

    /// <summary>
    /// Task list update payload from Companion.
    /// </summary>
    [Serializable]
    public class TaskListUpdate
    {
        [JsonProperty("tasks")]
        public List<TaskItem> Tasks { get; set; } = new List<TaskItem>();

        [JsonProperty("active_count")]
        public int ActiveCount { get; set; }
    }
}
