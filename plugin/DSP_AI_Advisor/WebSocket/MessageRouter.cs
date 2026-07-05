using System;
using System.Collections.Generic;
using DSP_AI_Advisor.Models;

namespace DSP_AI_Advisor.WebSocket
{
    /// <summary>
    /// Static message router — dispatches incoming WebSocket messages to registered handlers.
    /// All callbacks are invoked on the Unity main thread via UIManager.Update().
    /// </summary>
    public static class MessageRouter
    {
        // ── Delegates ──────────────────────────────────────────

        public delegate void TaskListHandler(List<TaskItem> tasks);
        public delegate void AgentProgressHandler(string phase, string message, float progressPct);
        public delegate void ConnectionHandler(bool connected);

        // ── Events ─────────────────────────────────────────────

        /// <summary>Fired when Companion sends a task_list_update.</summary>
        public static event TaskListHandler OnTaskListUpdate;

        /// <summary>Fired when Companion sends agent_progress.</summary>
        public static event AgentProgressHandler OnAgentProgress;

        /// <summary>Fired when client connects/disconnects.</summary>
        public static event ConnectionHandler OnConnectionChanged;

        // ── Dispatch ───────────────────────────────────────────

        /// <summary>
        /// Route an incoming message envelope to the appropriate event.
        /// Called from UIManager.Update() on the Unity main thread.
        /// </summary>
        public static void Dispatch(MessageEnvelope envelope)
        {
            if (envelope == null) return;

            try
            {
                switch (envelope.Channel)
                {
                    case "snapshot":
                        HandleSnapshot(envelope);
                        break;

                    case "command":
                        HandleCommand(envelope);
                        break;

                    default:
                        Plugin.Log.LogDebug(
                            $"[MessageRouter] Unknown channel: {envelope.Channel}");
                        break;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning(
                    $"[MessageRouter] Error dispatching {envelope.Channel}/{envelope.Type}: {ex.Message}");
            }
        }

        private static void HandleSnapshot(MessageEnvelope envelope)
        {
            switch (envelope.Type)
            {
                case "task_list_update":
                    if (!string.IsNullOrEmpty(envelope.Payload))
                    {
                        var update = Newtonsoft.Json.JsonConvert
                            .DeserializeObject<TaskListUpdate>(envelope.Payload);
                        if (update?.Tasks != null)
                        {
                            OnTaskListUpdate?.Invoke(update.Tasks);
                            Plugin.Log.LogInfo(
                                $"[MessageRouter] Task list: {update.Tasks.Count} tasks");
                        }
                    }
                    break;

                case "agent_progress":
                    if (!string.IsNullOrEmpty(envelope.Payload))
                    {
                        var prog = Newtonsoft.Json.JsonConvert
                            .DeserializeObject<AgentProgressPayload>(envelope.Payload);
                        if (prog != null)
                        {
                            OnAgentProgress?.Invoke(
                                prog.Phase ?? "",
                                prog.Message ?? "",
                                prog.ProgressPct);
                        }
                    }
                    break;
            }
        }

        private static void HandleCommand(MessageEnvelope envelope)
        {
            switch (envelope.Type)
            {
                case "heartbeat":
                    // Connection alive — trigger connection status update
                    OnConnectionChanged?.Invoke(true);
                    break;
            }
        }

        /// <summary>
        /// Call when WsServer detects client connect/disconnect.
        /// </summary>
        public static void NotifyConnection(bool connected)
        {
            OnConnectionChanged?.Invoke(connected);
        }
    }

    [Serializable]
    internal class AgentProgressPayload
    {
        [Newtonsoft.Json.JsonProperty("phase")]
        public string Phase { get; set; }

        [Newtonsoft.Json.JsonProperty("message")]
        public string Message { get; set; }

        [Newtonsoft.Json.JsonProperty("progress_pct")]
        public float ProgressPct { get; set; }
    }
}
