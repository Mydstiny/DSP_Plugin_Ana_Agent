using System;
using System.Collections.Generic;
using DSP_AI_Advisor.Models;
using DSP_AI_Advisor.WebSocket;
using UnityEngine;

namespace DSP_AI_Advisor.UI
{
    /// <summary>
    /// UI Manager — MonoBehaviour that orchestrates all UI panels.
    /// Owns task state, routes messages, renders panels in OnGUI.
    /// </summary>
    public class UIManager : MonoBehaviour
    {
        public static UIManager Instance { get; private set; }

        // ── Panel visibility ──────────────────────────────────

        public bool ShowControlPanel = false;
        public bool ShowTaskList = false;
        public bool ShowPlanetHUD = true;

        // ── State ─────────────────────────────────────────────

        private List<TaskItem> _tasks = new();
        private readonly object _taskLock = new();
        private string _agentProgressMessage = "";
        private float _agentProgressPct = 0f;
        private bool _isConnected = false;
        private DateTime _lastScanTime = DateTime.MinValue;
        private int _lastTaskCount = 0;

        // ── Window rects (draggable) ──────────────────────────

        private Rect _controlPanelRect = new Rect(20, 60, 280, 320);
        private Rect _taskListRect = new Rect(800, 60, 400, 500);
        private Vector2 _taskScrollPos = Vector2.zero;

        // ── Toggle key ────────────────────────────────────────

        private const KeyCode TOGGLE_KEY = KeyCode.F8;

        // ── Unity lifecycle ───────────────────────────────────

        void Awake()
        {
            if (Instance != null)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            // Register message callbacks
            MessageRouter.OnTaskListUpdate += HandleTaskListUpdate;
            MessageRouter.OnAgentProgress += HandleAgentProgress;
            MessageRouter.OnConnectionChanged += HandleConnectionChanged;
        }

        void Update()
        {
            // Toggle control panel
            if (Input.GetKeyDown(TOGGLE_KEY))
            {
                ShowControlPanel = !ShowControlPanel;
            }

            // Consume incoming WS messages on main thread
            while (WsServer.Instance.TryDequeueMessage(out var envelope))
            {
                MessageRouter.Dispatch(envelope);
            }
        }

        void OnGUI()
        {
            if (ShowControlPanel)
                DrawControlPanel();

            if (ShowTaskList)
                DrawTaskList();

            if (ShowPlanetHUD && _tasks.Count > 0)
                DrawPlanetHUD();
        }

        void OnDestroy()
        {
            MessageRouter.OnTaskListUpdate -= HandleTaskListUpdate;
            MessageRouter.OnAgentProgress -= HandleAgentProgress;
            MessageRouter.OnConnectionChanged -= HandleConnectionChanged;
        }

        // ── Message handlers ──────────────────────────────────

        private void HandleTaskListUpdate(List<TaskItem> tasks)
        {
            lock (_taskLock)
            {
                _tasks = tasks;
            }
            _lastScanTime = DateTime.UtcNow;
            _lastTaskCount = tasks.Count;

            // Auto-show task list when new results arrive
            if (tasks.Count > 0)
            {
                ShowTaskList = true;
            }

            Plugin.Log.LogInfo($"[UIManager] Received {tasks.Count} tasks");
        }

        private void HandleAgentProgress(string phase, string message, float pct)
        {
            _agentProgressPct = pct;
            _agentProgressMessage = $"[{phase}] {message}";
        }

        private void HandleConnectionChanged(bool connected)
        {
            _isConnected = connected;
        }

        // ── Panel rendering ───────────────────────────────────

        private void DrawControlPanel()
        {
            _controlPanelRect = GUILayout.Window(
                1001, _controlPanelRect, ControlPanelFunc,
                "DSP AI Advisor");
        }

        private void ControlPanelFunc(int windowId)
        {
            GUI.DragWindow(new Rect(0, 0, _controlPanelRect.width, 20));

            GUILayout.Space(25);

            // Connection status
            var statusColor = _isConnected ? "green" : "red";
            var statusIcon = _isConnected ? "✓" : "✗";
            GUILayout.Label(
                $"<color={statusColor}>{statusIcon} Companion: " +
                $"{(_isConnected ? "Connected" : "Disconnected")}</color>");

            GUILayout.Space(8);

            // Layer toggles
            GUILayout.Label("Mode Switches:", Plugin.Log is { } ? "" : "");
            GUILayout.BeginHorizontal();
            GUILayout.Label("Periodic Snapshot", GUILayout.Width(130));
            GUILayout.Label("ON", GUILayout.Width(30));
            GUILayout.EndHorizontal();

            GUILayout.BeginHorizontal();
            GUILayout.Label("Deep Analysis (AI)", GUILayout.Width(130));
            GUILayout.Label("ON", GUILayout.Width(30));
            GUILayout.EndHorizontal();

            GUILayout.Space(12);

            // Galaxy scan trigger
            GUI.backgroundColor = Color.cyan;
            if (GUILayout.Button("Start Full Galaxy Analysis", GUILayout.Height(36)))
            {
                TriggerGalaxyScan();
            }
            GUI.backgroundColor = Color.white;

            GUILayout.Space(8);

            // Agent progress
            if (!string.IsNullOrEmpty(_agentProgressMessage))
            {
                GUILayout.Label($"Agent: {_agentProgressMessage}");
                // Progress bar
                var barRect = GUILayoutUtility.GetRect(260, 18);
                GUI.Box(barRect, "");
                var fillRect = new Rect(
                    barRect.x + 2, barRect.y + 2,
                    (barRect.width - 4) * _agentProgressPct, barRect.height - 4);
                GUI.Box(fillRect, "");
            }

            GUILayout.Space(8);

            // Last scan info
            if (_lastScanTime != DateTime.MinValue)
            {
                var ago = (DateTime.UtcNow - _lastScanTime).TotalMinutes;
                GUILayout.Label(
                    $"Last analysis: {ago:F0} min ago → {_lastTaskCount} suggestions");
            }

            GUILayout.Space(12);

            // Action buttons
            GUILayout.BeginHorizontal();
            if (GUILayout.Button("Task List", GUILayout.Height(28)))
            {
                ShowTaskList = !ShowTaskList;
            }
            if (GUILayout.Button("Planet HUD", GUILayout.Height(28)))
            {
                ShowPlanetHUD = !ShowPlanetHUD;
            }
            GUILayout.EndHorizontal();
        }

        private void DrawTaskList()
        {
            _taskListRect = GUILayout.Window(
                1002, _taskListRect, TaskListFunc,
                $"Optimization Tasks (active: {ActiveTaskCount})");
        }

        private void TaskListFunc(int windowId)
        {
            GUI.DragWindow(new Rect(0, 0, _taskListRect.width, 20));

            var activeTasks = ActiveTasks;
            if (activeTasks.Count == 0)
            {
                GUILayout.Space(25);
                GUILayout.Label("No active tasks. Run a galaxy analysis first.");
                return;
            }

            GUILayout.Space(25);

            // Scroll view for task list
            _taskScrollPos = GUILayout.BeginScrollView(_taskScrollPos,
                GUILayout.Width(_taskListRect.width - 10),
                GUILayout.Height(_taskListRect.height - 40));

            string currentCategory = "";
            Color savedColor = GUI.color;

            foreach (var task in activeTasks)
            {
                // Category header
                if (task.Category != currentCategory)
                {
                    currentCategory = task.Category;
                    GUILayout.Space(4);
                    var catIcon = GetCategoryIcon(task.Category);
                    var catLabel = GetCategoryLabel(task.Category);
                    GUILayout.Label($"  {catIcon} {catLabel}");
                    GUILayout.Space(2);
                }

                // Priority color
                GUI.color = GetPriorityColor(task.Priority);

                // Task card
                GUILayout.BeginVertical("box");
                GUI.color = savedColor;

                // Title row
                GUILayout.BeginHorizontal();
                var prioIcon = GetPriorityIcon(task.Priority);
                GUI.color = GetPriorityColor(task.Priority);
                GUILayout.Label($"{prioIcon} {task.Title}");
                GUI.color = savedColor;

                if (!string.IsNullOrEmpty(task.Planet))
                {
                    GUILayout.FlexibleSpace();
                    GUILayout.Label($"[{task.Planet}]");
                }
                GUILayout.EndHorizontal();

                // Description
                if (!string.IsNullOrEmpty(task.Description))
                {
                    GUILayout.Label($"    {task.Description}");
                }

                // Action row
                GUILayout.BeginHorizontal();
                GUILayout.Label($"    Action: {task.SuggestedAction}",
                    GUILayout.Width(250));

                GUILayout.FlexibleSpace();

                if (task.Status == "new")
                {
                    if (GUILayout.Button("Track", GUILayout.Width(55)))
                    {
                        WsServer.Instance.SendCommand("track_task",
                            new { task_id = task.Id });
                        task.Status = "tracked";
                    }
                }
                else if (task.Status == "tracked")
                {
                    GUI.color = Color.green;
                    GUILayout.Label("▶ Active", GUILayout.Width(60));
                    GUI.color = savedColor;
                }

                if (GUILayout.Button("Ignore", GUILayout.Width(55)))
                {
                    WsServer.Instance.SendCommand("dismiss_task",
                        new { task_id = task.Id });
                    task.Status = "dismissed";
                }
                GUILayout.EndHorizontal();

                if (!string.IsNullOrEmpty(task.EstimatedEffort))
                {
                    GUILayout.Label($"    Est. time: {task.EstimatedEffort}");
                }

                GUILayout.EndVertical();
            }

            GUILayout.EndScrollView();
        }

        private void DrawPlanetHUD()
        {
            var hudRect = new Rect(20, Screen.height - 200, 260, 180);
            GUILayout.Window(1003, hudRect, PlanetHUDFunc, "Planet Status");
        }

        private void PlanetHUDFunc(int windowId)
        {
            GUI.DragWindow(new Rect(0, 0, 260, 20));
            GUILayout.Space(22);

            // Group tasks by planet
            var byPlanet = GetTasksByPlanet();
            if (byPlanet.Count == 0)
            {
                GUILayout.Label("No planet issues.");
                return;
            }

            foreach (var kvp in byPlanet)
            {
                GUILayout.Label($"► {kvp.Key}");
                foreach (var task in kvp.Value.Take(3))  // max 3 per planet
                {
                    var icon = GetCategoryIcon(task.Category);
                    GUI.color = GetPriorityColor(task.Priority);
                    GUILayout.Label($"    {icon} {task.Title}");
                }
            }
            GUI.color = Color.white;
        }

        // ── Helpers ───────────────────────────────────────────

        private List<TaskItem> ActiveTasks
        {
            get
            {
                lock (_taskLock)
                {
                    return _tasks.FindAll(t => t.IsActive);
                }
            }
        }

        private int ActiveTaskCount
        {
            get
            {
                lock (_taskLock)
                {
                    return _tasks.FindAll(t => t.IsActive).Count;
                }
            }
        }

        private Dictionary<string, List<TaskItem>> GetTasksByPlanet()
        {
            var result = new Dictionary<string, List<TaskItem>>();
            lock (_taskLock)
            {
                foreach (var task in _tasks)
                {
                    if (!task.IsActive) continue;
                    var key = task.Planet ?? "Global";
                    if (!result.ContainsKey(key))
                        result[key] = new List<TaskItem>();
                    result[key].Add(task);
                }
            }
            return result;
        }

        private void TriggerGalaxyScan()
        {
            _agentProgressMessage = "Triggering galaxy scan...";
            _agentProgressPct = 0f;
            _lastScanTime = DateTime.UtcNow;

            WsServer.Instance.SendCommand("trigger_scan");
            Plugin.Log.LogInfo("[UIManager] Galaxy scan triggered");
        }

        // ── Visual helpers ────────────────────────────────────

        private static Color GetPriorityColor(string priority)
        {
            switch (priority)
            {
                case "critical": return new Color(1f, 0.3f, 0.3f);   // red
                case "high": return new Color(1f, 0.6f, 0.2f);       // orange
                case "medium": return new Color(1f, 0.9f, 0.3f);     // yellow
                case "low": return new Color(0.4f, 0.9f, 0.4f);      // green
                default: return Color.white;
            }
        }

        private static string GetPriorityIcon(string priority)
        {
            switch (priority)
            {
                case "critical": return "!!";
                case "high": return "!";
                case "medium": return "•";
                case "low": return ">";
                default: return " ";
            }
        }

        private static string GetCategoryIcon(string category)
        {
            switch (category)
            {
                case "power": return "(P)";
                case "production": return "(M)";
                case "logistics": return "(L)";
                case "upgrade": return "(U)";
                default: return "(?)";
            }
        }

        private static string GetCategoryLabel(string category)
        {
            switch (category)
            {
                case "power": return "=== POWER ===";
                case "production": return "=== PRODUCTION ===";
                case "logistics": return "=== LOGISTICS ===";
                case "upgrade": return "=== UPGRADES ===";
                default: return $"=== {category.ToUpper()} ===";
            }
        }
    }
}
