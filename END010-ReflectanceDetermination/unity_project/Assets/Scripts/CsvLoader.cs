using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEngine;

[RequireComponent(typeof(LightCurveGenerator))]
[DefaultExecutionOrder(-200)]

public class CsvLoader : MonoBehaviour
{
    [Tooltip("Absolute or relative path of the orbit/attitude csv(e.g. Assets/csvUnity.csv)")]
    public string CSVFile = "Assets/dummy.csv";

    private LightCurveGenerator LightCurveGenerator;

    // Unity's own CLI flags
    private static readonly Dictionary<string, bool> UnityFlags = new()
    {
        // Unity
        { "-batchmode", false }, { "-nographics", false }, { "-silent-crashes", false },
        { "-logfile",   true  }, { "-logFile",   true  },  { "-quit",           false },
        { "-stackTraceLogType", true }, { "-vrmode", true }, { "-disable-assembly-updater", false },

        // Hub
        { "-useHub", false }, { "-hubIPC", false }, { "-hubSessionId", true },
        { "-cloudEnvironment", true }, { "-projectpath", true }, { "-projectPath", true },
        { "-pid", true }, { "-licensingIpc", true }, { "-accessToken", true },
    };

    private void Start()
    {
        LightCurveGenerator = GetComponent<LightCurveGenerator>();

        Debug.Log("CsvLoader: Start");

        // Parse CLI arguments
        ParseCommandLineArgs();
        // Parse input csv
        var (timeStamp, objPos, camPos, sunPos, objRot, objRng, objEl, sunRng) = ParseCsvFile(CSVFile);
        if (objPos.Count == 0)
        {
            Debug.LogError("CsvLoader: No rows parsed.");
            return;
        }

        // Push geometry into the LightCurveGenerator
        LightCurveGenerator.PushGeometry(objPos, camPos, sunPos, objRot, timeStamp, objEl, objRng, sunRng);
        
        Debug.Log($"Loaded {objPos.Count} frames geometries.");

        // Start light curve generator routine
        StartCoroutine(LightCurveGenerator.CaptureKeyFrames());
    }

    /* ==================================================================
     *  HELPERS
     * ================================================================== */

    // Method to parse the input csv file to save the orbit geoemtry (onj, cam, sun) and the object rotation at each frame
    private (List<string>, List<Vector3>, List<Vector3>, List<Vector3>, List<Quaternion>, List<float>, List<float>, List<float>) ParseCsvFile(string path)
    {
        Debug.Log("CsvLoader: Parse CSV file");
        if (!File.Exists(path))
        {
            Debug.LogError($"CsvLoader: csv file not found: {path}");
            return (new(), new(), new(), new(), new(), new(), new(), new());
        }
        // Declare lists
        List<string> timeStamp  = new List<string>();
        List<Vector3> objPos    = new List<Vector3>();
        List<Vector3> camPos    = new List<Vector3>();
        List<Vector3> sunPos    = new List<Vector3>();
        List<float> objRng      = new List<float>();
        List<float> objEl       = new List<float>();
        List<float> sunRng      = new List<float>();
        List<Quaternion> objRot = new List<Quaternion>();

        // Iterate on each line of the CSV file
        try
        {
            foreach (string raw in File.ReadLines(path))
            {
                // Trim whitespaces
                string line = raw.Trim();
                // Check if data exists
                if (string.IsNullOrWhiteSpace(line) || line.StartsWith("#")) continue;
                string[] v = line.Split(',');
                // Skip header if it exists
                //if (!double.TryParse(v[0], NumberStyles.Any, CultureInfo.InvariantCulture, out _)) continue;
                // Check length
                if (v.Length < 17)
                {
                    Debug.LogError($"CSV line not correct: {line}. To generate a single light curve at least 17 parameters are required: 1 datetime, 3x3 obj, sun, cam ECI positions, object elevation, object range, sun range and 4 quaternion components. {v.Length} were provided");
                    return (new(), new(), new(), new(), new(), new(), new(), new());
                }

                static float ValuesParser(string s) => float.Parse(s, CultureInfo.InvariantCulture);

                // Parse time
                timeStamp.Add(v[0]);
                
                // Parse positions
                objPos.Add(ConvertRightHandedToLeftHandedVector(new Vector3(ValuesParser(v[1]), ValuesParser(v[2]), ValuesParser(v[3]))));
                camPos.Add(ConvertRightHandedToLeftHandedVector(new Vector3(ValuesParser(v[4]), ValuesParser(v[5]), ValuesParser(v[6]))));
                sunPos.Add(ConvertRightHandedToLeftHandedVector(new Vector3(ValuesParser(v[7]), ValuesParser(v[8]), ValuesParser(v[9]))));

                // Parse elevation and range
                objEl.Add(ValuesParser(v[10]));
                objRng.Add(ValuesParser(v[11]));
                sunRng.Add(ValuesParser(v[12]));

                // Parse quaternion
                objRot.Add(ConvertRightHandedToLeftHandedQuaternion(new Quaternion(ValuesParser(v[14]), ValuesParser(v[15]), ValuesParser(v[16]), ValuesParser(v[13]))));

            }
        }
        catch (Exception ex)
        {
            Debug.LogError($"CsvLoader: An error occurred: {ex.Message}");
#if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
#else
Application.Quit();                               
#endif
        }
        // Check: no rows parsed
        if (objPos.Count == 0)
        {
            Debug.LogError("CsvLoader: no data rows parsed.");
            return (new(), new(), new(), new(), new(), new(), new(), new());
        }
        // Check: all lists same length
        if ( !(objPos.Count == camPos.Count && camPos.Count == sunPos.Count && sunPos.Count == objRot.Count))
        {
            Debug.LogError($"CsvLoader: length mismatch: obj {objPos.Count}, cam {camPos.Count}, sun {sunPos.Count}, rot {objRot.Count}");
            return (new(), new(), new(), new(), new(), new(), new(), new());
        }
        // Parsed lists
        Debug.Log($"CsvLoader: CSV read OK. Rows = {objPos.Count}");
        return (timeStamp, objPos, camPos, sunPos, objRot, objRng, objEl, sunRng);
    }

    // Method to convert an input right handed vector in unity left handed reference frame (y up)
    private static Vector3 ConvertRightHandedToLeftHandedVector(Vector3 rightHandedVector)
    {
        return new Vector3(rightHandedVector.x, rightHandedVector.z, rightHandedVector.y);
    }

    // Method to convert an input right handed quaternion in unity left handed reference frame, coherent with the method above
    private static Quaternion ConvertRightHandedToLeftHandedQuaternion(Quaternion rightHandedQuaternion)
    {
        return new Quaternion(-rightHandedQuaternion.x, -rightHandedQuaternion.z, -rightHandedQuaternion.y, rightHandedQuaternion.w);
    }
    
    // Method to parse command line arguments if present
    private void ParseCommandLineArgs()
    {
        // Load default arguments
        Arguments ArgsAll = new();

        // Help
        string help = "Allowed flags:\n" +
                              "-csvFile <path>\n" +
                              "-maxFrameToRender <int>\n-maxFrameToSave <int>\n" +
                              "-lightCurveFilename <name>\n-outputFolder <folder>\n" +
                              "-camWidth <int>\n-camHeight <int>\n" +
                              "-useLinearSpace\n-enableView\n-saveFrames\n" +
                              "-sceneScale <float> (STAR)\n-cubesatClass <1|2|3|6|12> (STAR, StarCubeSatSelector)";

        // Read CLI arguments
        string[] cli = Environment.GetCommandLineArgs();
        var seen = new HashSet<string>();
        for (int i = 0; i < cli.Length; i++)
        {
            string arg = cli[i];

            // Skip executable path
            if (!arg.StartsWith("-")) continue;
            // Show help if requested
            switch (arg)
            {
                case "-help":
                    Debug.Log(help);
#if UNITY_EDITOR
                    UnityEditor.EditorApplication.isPlaying = false;
#else
                    Application.Quit();
#endif
                    return;

                // CSVLoader
                case "-csvFile":
                    ArgsAll.CSVFile = TakeValue(cli, ref i);
                    seen.Add(arg);
                    break;

                // LightCurveGenerator
                case "-maxFrameToRender":
                    ArgsAll.MaxFramesToRender = TakeInt(cli, ref i);
                    seen.Add(arg);
                    break;
                case "-maxFrameToSave":
                    ArgsAll.MaxFramesToSave = TakeInt(cli, ref i);
                    seen.Add(arg);
                    break;
                case "-lightCurveFilename":
                    ArgsAll.LightCurveFilename = TakeValue(cli, ref i);
                    seen.Add(arg);
                    break;
                case "-outputFolder":
                    ArgsAll.OutputFolder = TakeValue(cli, ref i);
                    seen.Add(arg);
                    break;
                case "-camWidth":
                    ArgsAll.CaptureWidth = TakeInt(cli, ref i);
                    seen.Add(arg);
                    break;
                case "-camHeight":
                    ArgsAll.CaptureHeight = TakeInt(cli, ref i);
                    seen.Add(arg);
                    break;
                case "-exposure":
                    ArgsAll.Exposure = TakeFloat(cli, ref i);
                    seen.Add(arg);
                    break;
                case "-focalLength":
                    ArgsAll.FocalLength = TakeFloat(cli, ref i);
                    seen.Add(arg);
                    break;
                case "-camSize":
                    ArgsAll.CamSize = TakeFloat(cli, ref i);      // STAR: float (a CubeSat needs a fraction of a metre)
                    seen.Add(arg);
                    break;
                case "-sceneScale":
                    ArgsAll.SceneScale = TakeFloat(cli, ref i);   // STAR: divides the csv positions (km in STAR)
                    seen.Add(arg);
                    break;
                case "-useOrtographic":
                    ArgsAll.UseOrtographic = true;
                    seen.Add(arg);
                    break;
                case "-useLinearSpace":
                    ArgsAll.UseLinearSpace = true;
                    seen.Add(arg);
                    break;
                case "-enableView":
                    ArgsAll.EnableView = true;
                    seen.Add(arg);
                    break;
                case "-saveFrames":
                    ArgsAll.SaveFrames = true;
                    seen.Add(arg);
                    break;
                case "-drawAxis":
                    ArgsAll.DrawAxis = true;
                    seen.Add(arg);
                    break;
                case "-saveEXR":
                    ArgsAll.SaveEXR = true;
                    seen.Add(arg);
                    break;
                case "-sumFlux":
                    ArgsAll.SumFlux = true;
                    seen.Add(arg);
                    break;
                case "-shadowCast":
                    ArgsAll.ShadowCast = true;
                    seen.Add(arg);
                    break;
                case "-UseFacetSum":
                    ArgsAll.UseFacetSum = true;
                    seen.Add(arg);
                    break;
                case "-UseRadiometricModel":
                    ArgsAll.UseRadiometricModel = true;
                    seen.Add(arg);
                    break;

                default:
                    if (UnityFlags.TryGetValue(arg, out bool hasValue))
                    {
                        // Skip unity flags
                        if (hasValue && i + 1 < cli.Length && !cli[i + 1].StartsWith("-")) i++; 
                        break;
                    }
                    // Unknown flags '-flag': ignore; if next token is likely a value, skip it once
                    if (arg.StartsWith("-") && i + 1 < cli.Length && !cli[i + 1].StartsWith("-")) i++;
                    break;
            }
        }

        if (seen.Count > 0)
        {
            // Apply the parsed arguments
            ApplyArguments(ArgsAll, seen);
        }
        else
        {
            Debug.Log("CsvLoader: no CLI flags detected - keeping Inspector settings.");
        }

        // Helpers
        static string TakeValue(string[] arr, ref int i)
        {
            if (i + 1 >= arr.Length) return string.Empty;
            var v = arr[++i];
            if (v.Length >= 2 && v[0] == '"' && v[^1] == '"') v = v[1..^1];
            return v;
        }
        static int TakeInt(string[] arr, ref int i)
        {
            var s = TakeValue(arr, ref i);
            return int.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out int v) ? v : 0;
        }
        static float TakeFloat(string[] arr, ref int i)
        {
            var s = TakeValue(arr, ref i);
            return float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out float v) ? v : 0f;
        }
    }

    // Method to apply the input arguments
    private void ApplyArguments(Arguments a, HashSet<string> seen)
    {
        // CsvLoader fields
        if (seen.Contains("-csvFile")) CSVFile = a.CSVFile;

        // LightCurveGenerator fields
        if (seen.Contains("-lightCurveFilename")) LightCurveGenerator.LightCurveFilename = a.LightCurveFilename;
        if (seen.Contains("-outputFolder")) LightCurveGenerator.OutputFolder = a.OutputFolder;
        if (seen.Contains("-maxFrameToRender")) LightCurveGenerator.MaxFramesToRender = a.MaxFramesToRender;
        if (seen.Contains("-maxFrameToSave")) LightCurveGenerator.MaxFramesToSave = a.MaxFramesToSave;
        if (seen.Contains("-camWidth")) LightCurveGenerator.CaptureWidth = a.CaptureWidth;
        if (seen.Contains("-camHeight")) LightCurveGenerator.CaptureHeight = a.CaptureHeight;
        if (seen.Contains("-exposure")) LightCurveGenerator.exposure = a.Exposure;
        if (seen.Contains("-focalLength")) LightCurveGenerator.FL = a.FocalLength;
        if (seen.Contains("-camSize")) LightCurveGenerator.camSize = a.CamSize;
        if (seen.Contains("-sceneScale") && a.SceneScale > 0f) LightCurveGenerator.SceneScale = a.SceneScale;
        if (seen.Contains("-useOrtographic")) LightCurveGenerator.useOrtographic = a.UseOrtographic;
        if (seen.Contains("-useLinearSpace")) LightCurveGenerator.UseLinearSpace = a.UseLinearSpace;
        if (seen.Contains("-enableView")) LightCurveGenerator.EnableView = a.EnableView;
        if (seen.Contains("-saveFrames")) LightCurveGenerator.SaveFrames = a.SaveFrames;
        if (seen.Contains("-drawAxis")) LightCurveGenerator.DrawAxis = a.DrawAxis;
        if (seen.Contains("-saveEXR")) LightCurveGenerator.SaveEXR = a.SaveEXR;

        if (seen.Contains("-sumFlux"))   LightCurveGenerator.SumFlux = a.SumFlux;
        if (seen.Contains("-shadowCast")) LightCurveGenerator.ShadowCast = a.ShadowCast;
        if (seen.Contains("-UseRadiometricModel")) LightCurveGenerator.UseRadiometricModel = a.UseRadiometricModel;
        if (seen.Contains("-UseFacetSum"))LightCurveGenerator.UseFacetSum = a.UseFacetSum;
    }

    // Arguments dictionary with defaults
    public class Arguments
    {
        public string CSVFile              = null;
        public string LightCurveFilename   = "lightcurve.csv";
        public string OutputFolder         = "Frames";
        public int    MaxFramesToRender    = 200;
        public int    MaxFramesToSave      = 100;
        public int    CaptureWidth         = 1024;
        public int    CaptureHeight        = 1024;
        public float  CamSize              = 5f;
        public bool   UseOrtographic       = false;
        public bool   UseLinearSpace       = true;
        public bool   EnableView           = false;
        public bool   SaveFrames           = false;
        public bool   DrawAxis             = false;
        public bool   SaveEXR              = false;
        public float  Exposure             = 1f;
        public float  FocalLength          = 1800f;
        public float  SceneScale           = 10000000f;
        public bool   SumFlux              = false;
        public bool   ShadowCast           = true;
        public bool   UseFacetSum          = false;
        public bool   UseRadiometricModel  = false;
    }


}