using System;
using BepInEx;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;

namespace DSP_AI_Advisor
{
    [BepInPlugin(PluginInfo.PLUGIN_GUID, PluginInfo.PLUGIN_NAME, PluginInfo.PLUGIN_VERSION)]
    public class Plugin : BaseUnityPlugin
    {
        internal static ManualLogSource Log;

        private Harmony _harmony;

        private void Awake()
        {
            Log = Logger;
            Log.LogInfo($"DSP AI Advisor v{PluginInfo.PLUGIN_VERSION} loading...");

            try
            {
                // 注册 Harmony 补丁
                _harmony = new Harmony(PluginInfo.PLUGIN_GUID);
                _harmony.PatchAll();

                Log.LogInfo("Harmony patches applied successfully.");

                // 启动 WebSocket Server
                WebSocket.WsServer.Instance.Start();

                // 创建 UI Manager GameObject
                var uiGo = new GameObject("DSP_AI_Advisor_UIManager");
                DontDestroyOnLoad(uiGo);
                uiGo.AddComponent<UI.UIManager>();

                Log.LogInfo("DSP AI Advisor loaded.");
            }
            catch (Exception ex)
            {
                Log.LogError($"Failed to initialize: {ex}");
            }
        }

        private void OnDestroy()
        {
            WebSocket.WsServer.Instance.Stop();
            _harmony?.UnpatchSelf();
            Log.LogInfo("DSP AI Advisor unloaded.");
        }
    }

    internal static class PluginInfo
    {
        public const string PLUGIN_GUID = "com.dsp.ai.advisor";
        public const string PLUGIN_NAME = "DSP AI Advisor";
        public const string PLUGIN_VERSION = "0.1.0";
    }
}
