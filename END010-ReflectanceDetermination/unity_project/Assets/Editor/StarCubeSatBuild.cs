using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

// STAR END-010: builds the CubeSat scene from baseScene.unity and the Windows player used by the module.
//   Unity.exe -batchmode -quit -projectPath <this project> -executeMethod StarCubeSatBuild.BuildAll
//             [-starBuildOutput <folder>] -logFile <log>
// The satellite object (ObjectWrapper) gets the five NASA-style CDS CubeSat models (Input/cubesat_3d_models/cds_nasa_style_*, copied in
// Assets/Models/StarCubeSats) as children CubeSat_1U ... CubeSat_12U; StarCubeSatSelector keeps the one of -cubesatClass at run time.
public static class StarCubeSatBuild
{
    const string BaseScene = "Assets/Scenes/baseScene.unity";
    const string StarScene = "Assets/Scenes/StarCubeSat.unity";
    const string ModelFolder = "Assets/Models/StarCubeSats";
    static readonly int[] Classes = { 1, 2, 3, 6, 12 };

    // material of the OBJ (CDS NASA-style generator) -> material of the project (declared convention: no optical data is published for
    // these parts; the frame is aluminium with the aluminium BRDF LUT, the cells use the project's solar-array material, the panel
    // substrate and the cell borders are dark)
    static readonly Dictionary<string, string> MaterialMap = new()
    {
        { "rail", "Aluminium" }, { "structure", "Aluminium" }, { "solar_cell", "SolarArray" },
        { "panel_substrate", "Black" }, { "cell_border", "Black" },
    };

    public static void BuildAll()
    {
        BuildScene();
        BuildPlayer();
    }

    public static void BuildScene()
    {
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        var scene = EditorSceneManager.OpenScene(BaseScene, OpenSceneMode.Single);
        var wrapper = GameObject.Find("ObjectWrapper");
        if (wrapper == null) Fail("ObjectWrapper not found in " + BaseScene);

        // the satellite model of the base scene is removed (its asset is not in the STAR copy of the project)
        var old = wrapper.transform.Cast<Transform>().Select(t => t.gameObject).ToList();
        foreach (var go in old)
        {
            if (PrefabUtility.IsPartOfPrefabInstance(go) && !PrefabUtility.IsPrefabAssetMissing(go))
                PrefabUtility.UnpackPrefabInstance(PrefabUtility.GetOutermostPrefabInstanceRoot(go), PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
            UnityEngine.Object.DestroyImmediate(go);
        }

        var projectMats = new Dictionary<string, Material>();
        foreach (var name in MaterialMap.Values.Distinct())
        {
            var m = AssetDatabase.LoadAssetAtPath<Material>($"Assets/Materials/{name}.mat");
            if (m == null) Fail($"material {name} not found");
            projectMats[name] = m;
        }

        foreach (int u in Classes)
        {
            string path = $"{ModelFolder}/CDS_{u}U_nasa_style.obj";
            var asset = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (asset == null) Fail("model not found: " + path);
            var go = (GameObject)PrefabUtility.InstantiatePrefab(asset, wrapper.transform);
            PrefabUtility.UnpackPrefabInstance(go, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
            go.name = $"CubeSat_{u}U";
            go.transform.localPosition = Vector3.zero;
            go.transform.localRotation = Quaternion.identity;
            go.transform.localScale = Vector3.one;          // the models are in metres, origin at the centre, Z along the long axis
            int unmapped = 0;
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                {
                    string key = mats[i] == null ? "" : mats[i].name;
                    if (MaterialMap.TryGetValue(key, out var target)) mats[i] = projectMats[target];
                    else { mats[i] = projectMats["Aluminium"]; unmapped++; }
                }
                r.sharedMaterials = mats;
            }
            if (unmapped > 0) Debug.LogWarning($"StarCubeSatBuild: {unmapped} material slot(s) of {go.name} not in the map: Aluminium used");
            go.SetActive(u == 6);
        }

        if (wrapper.GetComponent<StarCubeSatSelector>() == null)
            wrapper.AddComponent<StarCubeSatSelector>();
        // flags that runUnity.m can only switch on (a boolean flag is passed only when true): STAR's defaults are off
        var lcg = wrapper.GetComponent<LightCurveGenerator>();
        if (lcg == null) Fail("LightCurveGenerator not found on ObjectWrapper");
        lcg.DrawAxis = false;
        lcg.EnableView = false;
        lcg.SaveEXR = false;
        lcg.UseFacetSum = false;
        lcg.UseRadiometricModel = false;
        EditorUtility.SetDirty(lcg);

        if (!EditorSceneManager.SaveScene(scene, StarScene)) Fail("cannot save " + StarScene);
        AssetDatabase.SaveAssets();
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(StarScene, true) };
        Debug.Log("StarCubeSatBuild: scene saved " + StarScene);
    }

    public static void BuildPlayer()
    {
        string outFolder = ArgValue("-starBuildOutput")
                           ?? Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "lib", "BuildCubeSat"));
        Directory.CreateDirectory(outFolder);
        var options = new BuildPlayerOptions
        {
            scenes = new[] { StarScene },
            locationPathName = Path.Combine(outFolder, "UnityLightCurveInversion.exe"),
            target = BuildTarget.StandaloneWindows64,
            options = BuildOptions.None,
        };
        BuildReport report = BuildPipeline.BuildPlayer(options);
        if (report.summary.result != BuildResult.Succeeded)
            Fail($"build {report.summary.result}: {report.summary.totalErrors} error(s)");
        Debug.Log($"StarCubeSatBuild: player built in {outFolder} ({report.summary.totalSize} bytes)");
    }

    static string ArgValue(string flag)
    {
        var args = Environment.GetCommandLineArgs();
        for (int i = 0; i + 1 < args.Length; i++)
            if (args[i] == flag) return args[i + 1];
        return null;
    }

    static void Fail(string message)
    {
        Debug.LogError("StarCubeSatBuild: " + message);
        if (Application.isBatchMode) EditorApplication.Exit(1);
        throw new Exception(message);
    }
}
