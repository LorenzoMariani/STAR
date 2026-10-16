using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Xml.Linq;
using Unity.Mathematics;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using Unity.Collections;
using System.Linq.Expressions;
using Unity.VisualScripting;

public class LightCurveGenerator : MonoBehaviour
{
    #region === Inspector References ==========================================================
    [Header("Scene references")]
    public GameObject satellite = null!;
    public Light sun = null!;
    public Camera observer = null!;

    [Header("Capture settings")]
    [Tooltip("What kind of camera you want to use? If true ortographic, otherwise perspective")]
    public bool useOrtographic = false;
    [Tooltip("Ortographic camera size")]
    public float camSize = 5f;
    // STAR: scale that divides the csv positions (render mode); 1e7 is the value of the working copy, STAR passes -sceneScale 100 (km)
    public float SceneScale = 10000000f;
    [Tooltip("Perspective camera focal length in mm")]
    public float FL = 1800f;
    [Tooltip("Perspective camera sensor size in mm")]
    public float sensorSize = 22.5f;
    [Tooltip("Horizontal resolution for SAVED frames")]
    public int CaptureWidth = 512;
    [Tooltip("Vertical resolution for SAVED frames")]
    public int CaptureHeight = 512;
    [Tooltip("Show camera in editor (otherwise off-screen)")]
    public bool EnableView = false;
    [Tooltip("Enable PNG/EXR saving for the first MaxFramesToSave frames")]
    public bool SaveFrames = false;
    [Tooltip("Write EXR instead of PNG when saving frames (HDR)")]
    public bool SaveEXR = false;
    [Tooltip("Increase PNG exposure for better viewwing (only applies if saveEXR is unticked).")]
    public float exposure = 1f;
    [Tooltip("Draw sat and sun axis on saved frames")]
    public bool DrawAxis   = false;
    [Tooltip("How many key frames to render (<= CSV rows).")]
    public int MaxFramesToRender = 100;
    [Tooltip("How many key frames to save (<= MaxFramesToRender).")]
    public int MaxFramesToSave = 100;
    [Tooltip("Enable shadow casting from the sun")]
    public bool ShadowCast = true;
    [Tooltip("Output CSV name with extension")]
    public string LightCurveFilename = "lightcurve.csv";
    [Tooltip("Folder name (relative or absolute) for frames/CSV")]
    public string OutputFolder = "Frames";
    [Tooltip("Use linear color space")]
    public bool UseLinearSpace = true;
    [Tooltip("Compute integrated flux (sum) rather than average luminance.")]
    public bool SumFlux = false;

    [Header("Radiometric model")]
    [Tooltip("CSV: wavelength_nm,value  (e.g., ASTM AM1.5 or AM0). Units: W m^-2 nm^-1 at 1 AU.")]
    public string SunSpectrumCSV;
    [Tooltip("CSV: wavelength_nm,value  (0..1). Camera quantum efficiency")]
    public string QECSV;
    [Tooltip("CSV: wavelength_nm,value  (0..1). Camera window transmission")]
    public string WTCSV;
    [Tooltip("f-number of the optical system. For 1200/250 → 4.8.")]
    public float FNumber = 4.8f;
    [Tooltip("Diameter of the optical system in meters")]
    public float Dm = 0.25f;
    [Tooltip("Pixel size (micrometers). Marana: 11")]
    public float PixelSizeUM = 11.0f;
    [Tooltip("Exposure time (seconds).")]
    public float ExposureSeconds = 0.06f;
    [Tooltip("Camera gain (e to ADU)")]
    public float gain = 0.77f;
    [Tooltip("Use or not radiometric model")]
    public bool UseRadiometricModel = false;

    [Header("Facet model")]
    [Tooltip("Use analytic facet-sum instead of rasterizing.")]
    public bool UseFacetSum = false;

    [Header("Debug")]
    [Tooltip("If true, writes all pixel values of frame 0 to a CSV in OutputFolder.")]
    public bool DebugFirstFramePixels = false;
    [Tooltip("File name for the pixel dump (written to OutputFolder).")]
    public string PixelDebugFilename = "frame0_pixels.csv";


[Header("BRDF LUT shading (material -> LUT)")]
[Tooltip("If enabled, binds per-material BRDF LUT buffers/metadata to the Custom/brdfLut shader using MaterialPropertyBlocks.")]
public bool UseBrdfLuts = true;

[Serializable]
public class MaterialLutBinding
{
    [Tooltip("Material asset to match against Renderer.sharedMaterials slots.")]
    public Material material = null!;

    [Tooltip("Exported LUT binary payload (.bytes). Import in Unity as a TextAsset.")]
    public TextAsset lutBytes = null!;

    [Tooltip("Exported LUT metadata (.xml). Import in Unity as a TextAsset.")]
    public TextAsset lutXml = null!;

    [Tooltip("Target wavelengths (nm) to map multi-band LUT -> RGB (nearest band is used).")]
    public Vector3 targetWavelengthsRGB = new Vector3(630f, 530f, 470f);

    [Range(0f, 10f)]
    public float lutIntensity = 1.0f;

    public bool debugOutOfRange = true;
}

[Tooltip("Associate each material with its lookup table.")]
public List<MaterialLutBinding> MaterialLuts = new List<MaterialLutBinding>();
    #endregion

    #region === Buffers (external) ============================================================
    [HideInInspector] public List<Vector3> objectPositions = new();
    [HideInInspector] public List<Vector3> observerPositions = new();
    [HideInInspector] public List<Vector3> sunPositions = new();
    [HideInInspector] public List<Quaternion> objectRotations = new();
    [HideInInspector] public List<float> objectRange = new();
    [HideInInspector] public List<float> objectElevation = new();
    [HideInInspector] public List<float> sunRange = new();
    [HideInInspector] public List<string> timeStamp = new();

    public FacetFluxIntegrator FluxIntegrator;
    #endregion

    #region === Internals =====================================================================
    private readonly List<string> _csv = new();

    // Full-resolution textures
    RenderTexture _rtFull = null!;
    Texture2D _texFull = null!;
    Rect _fullRect;

    // Check if project is linear
    private bool _projectLinear;

    // Fixed clip planes
    private float _nearFixed, _farFixed;
    private bool _clipInitialized = false;
    private const float kMinNearClip = 0.05f;
    private const float kMinClipSpan = 0.50f;

    private bool _debuggedPixels = false;

    // Physical constants
    private const double H = 6.62607015e-34;
    private const double C = 2.99792458e8;
    private const double AU_KM = 149597870.700;
    // Passbands
    private const double Bmin = 425.0;
    private const double Bmax = 500.0;
    private const double Gmin = 500.0;
    private const double Gmax = 580.0;
    private const double Rmin = 580.0;
    private const double Rmax = 702.5;
    private Vector3 _lastSunDirW, _lastSatPosW;
    #endregion

    #region === Structs =======================================================================
    private struct Curve { public float[] lam_nm; public float[] y; }
    Curve _Esun, _QE, _WT, _Tatm;
    private bool _spectraReady = false;
    private struct Colors { public float sumR, sumG, sumB, sumY; public int count; }


    #region === BRDF LUT binding internals =====================================================
    private struct LutMeta
{
    public int nAzL, nThL, nAzC, nThC;
    public float azMinL, thMinL, azMinC, thMinC;
    public float azStepL, thStepL, azStepC, thStepC;
    public int nBands;
    public int floatsPerPoint; // includes padding to float4 blocks
    public float[] wavelengthCenters;
}

    private struct LutGpuResource
{
    public ComputeBuffer buffer;
    public LutMeta meta;
}

    private readonly Dictionary<Material, LutGpuResource> _lutByMaterial = new Dictionary<Material, LutGpuResource>();
    #endregion
    #endregion

    #region === Lifecycle =====================================================================
    // First actions performed when the program is called (just once)
    private void Awake()
    {
        _projectLinear = QualitySettings.activeColorSpace == ColorSpace.Linear;
    }
    // Actions to be performed once the program is started (after awake - csvLoader done)
    private void Start()
    {
        ConfigureSun();
        ConfigureCamera();
        Directory.CreateDirectory(OutputFolder);
        if (!UseFacetSum)
        {
            EnsureRenderTargets();
            ApplyUniformScale(SceneScale);
        }
        EnsureSpectra();
    
        if (UseBrdfLuts)
        {
            ApplyBrdfLutBindings();
        }
    }
    // Actions to be performed on env destroy
    private void OnDestroy()
    {
        ReleaseRT(ref _rtFull);
        if (_texFull) Destroy(_texFull);
        ReleaseBrdfLutResources();
    }
    #endregion

    #region === BRDF LUT binding (material -> LUT) ============================================
    [ContextMenu("Apply BRDF LUT Bindings")]
    public void ApplyBrdfLutBindings()
    {
        // Clear any previous resources
        ReleaseBrdfLutResources();

        if (MaterialLuts == null || MaterialLuts.Count == 0)
            return;

        // Load LUT resources per material
        foreach (var b in MaterialLuts)
        {
            if (b == null || b.material == null || b.lutBytes == null || b.lutXml == null)
                continue;

            if (_lutByMaterial.ContainsKey(b.material))
                continue; // first binding wins for a given material

            try
            {
                var res = LoadLutToGpu(b.lutBytes, b.lutXml, b.targetWavelengthsRGB);
                _lutByMaterial[b.material] = res;
            }
            catch (Exception ex)
            {
                Debug.LogError($"BRDF LUT: Failed to load for material '{b.material.name}': {ex.Message}");
            }
        }

        if (_lutByMaterial.Count == 0)
            return;

        // Apply property blocks per renderer material slot
        var renderers = GetComponentsInChildren<Renderer>(includeInactive: true);
        foreach (var r in renderers)
        {
            if (r == null) continue;
            var mats = r.sharedMaterials;
            if (mats == null) continue;

            for (int mi = 0; mi < mats.Length; mi++)
            {
                var mat = mats[mi];
                if (mat == null) continue;

                // Find binding for this exact material asset
                var binding = MaterialLuts.FirstOrDefault(x => x != null && x.material == mat);
                if (binding == null) continue;

                if (!_lutByMaterial.TryGetValue(mat, out var res))
                    continue;

                var mpb = new MaterialPropertyBlock();
                r.GetPropertyBlock(mpb, mi);

                // Shader inputs (must match brdfLut.shader)
                mpb.SetBuffer("_BrdfLutRgb", res.buffer);
                mpb.SetInt("_nAzL", res.meta.nAzL);
                mpb.SetInt("_nThL", res.meta.nThL);
                mpb.SetInt("_nAzC", res.meta.nAzC);
                mpb.SetInt("_nThC", res.meta.nThC);

                mpb.SetFloat("_azMinL", res.meta.azMinL);
                mpb.SetFloat("_thMinL", res.meta.thMinL);
                mpb.SetFloat("_azMinC", res.meta.azMinC);
                mpb.SetFloat("_thMinC", res.meta.thMinC);

                mpb.SetFloat("_azStepL", res.meta.azStepL);
                mpb.SetFloat("_thStepL", res.meta.thStepL);
                mpb.SetFloat("_azStepC", res.meta.azStepC);
                mpb.SetFloat("_thStepC", res.meta.thStepC);

                mpb.SetFloat("_LutIntensity", Mathf.Clamp(binding.lutIntensity, 0f, 10f));
                mpb.SetFloat("_DebugOutOfRange", binding.debugOutOfRange ? 1f : 0f);

                r.SetPropertyBlock(mpb, mi);
            }
        }
    }

    private void ReleaseBrdfLutResources()
    {
        if (_lutByMaterial.Count == 0) return;
        foreach (var kv in _lutByMaterial)
        {
            try { if (kv.Value.buffer != null) kv.Value.buffer.Release(); }
            catch { /* ignore */ }
        }
        _lutByMaterial.Clear();
    }

    private LutGpuResource LoadLutToGpu(TextAsset bytesAsset, TextAsset xmlAsset, Vector3 targetWlRgb)
    {
        var meta = ParseXmlMeta(xmlAsset.text);

        int nPoints = meta.nAzL * meta.nThL * meta.nAzC * meta.nThC;
        if (nPoints <= 0)
            throw new Exception("Invalid LUT dimensions parsed from XML.");

        if (bytesAsset.bytes == null || bytesAsset.bytes.Length == 0)
            throw new Exception("LUT .bytes is empty.");
        if ((bytesAsset.bytes.Length % 4) != 0)
            throw new Exception("LUT .bytes length is not a multiple of 4 (single-precision floats expected).");

        int totalFloats = bytesAsset.bytes.Length / 4;
        int floatsPerPoint = totalFloats / nPoints;
        if (floatsPerPoint <= 0 || floatsPerPoint * nPoints != totalFloats)
            throw new Exception("LUT .bytes size is not consistent with XML size4 (points).");

        // If XML provides floatsPerPoint, verify it
        if (meta.floatsPerPoint > 0 && meta.floatsPerPoint != floatsPerPoint)
            Debug.LogWarning($"BRDF LUT: XML floatsPerPoint={meta.floatsPerPoint} but derived={floatsPerPoint}. Using derived.");

        meta.floatsPerPoint = floatsPerPoint;

        // Convert bytes -> float[] (little-endian)
        var floats = new float[totalFloats];
        Buffer.BlockCopy(bytesAsset.bytes, 0, floats, 0, bytesAsset.bytes.Length);

        // Determine band indices to map to RGB. Export packs bands first, then padding.
        int nBands = meta.nBands > 0 ? meta.nBands : Mathf.Min(3, floatsPerPoint);
        nBands = Mathf.Clamp(nBands, 1, floatsPerPoint);
        int idxR = 0, idxG = Mathf.Min(1, nBands - 1), idxB = Mathf.Min(2, nBands - 1);

        if (meta.wavelengthCenters != null && meta.wavelengthCenters.Length >= nBands)
        {
            idxR = NearestIndex(meta.wavelengthCenters, targetWlRgb.x, nBands);
            idxG = NearestIndex(meta.wavelengthCenters, targetWlRgb.y, nBands);
            idxB = NearestIndex(meta.wavelengthCenters, targetWlRgb.z, nBands);
        }

        idxR = Mathf.Clamp(idxR, 0, nBands - 1);
        idxG = Mathf.Clamp(idxG, 0, nBands - 1);
        idxB = Mathf.Clamp(idxB, 0, nBands - 1);

        // Build float4 per LUT point: xyz = RGB
        var v4 = new Vector4[nPoints];
        for (int p = 0; p < nPoints; p++)
        {
            int off = p * floatsPerPoint;
            float r = floats[off + idxR];
            float g = floats[off + idxG];
            float b = floats[off + idxB];
            v4[p] = new Vector4(r, g, b, 1f);
        }

        var buffer = new ComputeBuffer(nPoints, sizeof(float) * 4, ComputeBufferType.Structured);
        buffer.SetData(v4);

        return new LutGpuResource { buffer = buffer, meta = meta };
    }

    private static LutMeta ParseXmlMeta(string xml)
    {
        var doc = XDocument.Parse(xml);
        var root = doc.Root;
        if (root == null || root.Name.LocalName != "LUTMetadata")
            throw new Exception("Invalid LUT XML: expected <LUTMetadata> root.");

        int[] size4 = root.Element("size4")?.Elements("d")
            .Select(e => int.Parse(e.Value, CultureInfo.InvariantCulture)).ToArray()
            ?? throw new Exception("Missing <size4> in LUT XML.");
        if (size4.Length != 4) throw new Exception("<size4> must have 4 <d> entries.");

        float[] axisMin = root.Element("axisMin")?.Elements("min")
            .Select(e => float.Parse(e.Value, CultureInfo.InvariantCulture)).ToArray()
            ?? throw new Exception("Missing <axisMin> in LUT XML.");
        float[] axisStep = root.Element("axisStep")?.Elements("step")
            .Select(e => float.Parse(e.Value, CultureInfo.InvariantCulture)).ToArray()
            ?? throw new Exception("Missing <axisStep> in LUT XML.");

        int nBands = 0;
        var nBandsEl = root.Element("nBands");
        if (nBandsEl != null) int.TryParse(nBandsEl.Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out nBands);

        int floatsPerPoint = 0;
        var fppEl = root.Element("pack")?.Element("floatsPerPoint");
        if (fppEl != null) int.TryParse(fppEl.Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out floatsPerPoint);

        float[] wlCenters = null;
        var centers = root.Element("wavelengthGrid")?.Element("centers")?.Elements("wl")
            .Select(e => float.Parse(e.Value, CultureInfo.InvariantCulture)).ToArray();
        if (centers != null && centers.Length > 0) wlCenters = centers;

        return new LutMeta
        {
            nAzL = size4[0], nThL = size4[1], nAzC = size4[2], nThC = size4[3],
            azMinL = axisMin[0], thMinL = axisMin[1], azMinC = axisMin[2], thMinC = axisMin[3],
            azStepL = axisStep[0], thStepL = axisStep[1], azStepC = axisStep[2], thStepC = axisStep[3],
            nBands = nBands,
            floatsPerPoint = floatsPerPoint,
            wavelengthCenters = wlCenters
        };
    }

    private static int NearestIndex(float[] arr, float target, int limit)
    {
        int n = Mathf.Clamp(limit, 1, arr.Length);
        int best = 0;
        float bestD = Mathf.Abs(arr[0] - target);
        for (int i = 1; i < n; i++)
        {
            float d = Mathf.Abs(arr[i] - target);
            if (d < bestD) { bestD = d; best = i; }
        }
        return best;
    }
    #endregion

    #region === CSV-driven batch render =======================================================
    public IEnumerator CaptureKeyFrames()
    {
        // Frames to render with check
        int n = Mathf.Min(MaxFramesToRender, objectPositions.Count);
        if (n <= 0)
        {
            Debug.LogError("LightCurveGenerator: no key frames to render!");
            yield break;
        }
        // Mismatch check
        if (observerPositions.Count < n || sunPositions.Count < n)
        {
            Debug.LogError("LightCurveGenerator: geometry lists have inconsistent lengths.");
            yield break;
        }

        // Init output csv
        _csv.Clear();

        if (!UseFacetSum)
        {
            // Init
            _csv.Add("time,lum,R,G,B");
            EnsureRenderTargets();
            observer.targetTexture = _rtFull;
            observer.Render();
            observer.targetTexture = null;
            yield return null; 
        }
        else
        {
            _csv.Add("time,lum");
        }

        // Main loop
        for (int i = 0; i < n; i++)
        {
            SetGeometry(i);

            if (UseFacetSum)
            {
                if (FluxIntegrator == null)
                {
                    Debug.LogError("LightCurveGenerator: FluxIntegrator not assigned.");
                    yield break;
                }

                // Facets flux sum
                var (adu, electrons) = FluxIntegrator.ComputeFrameFlux(
                    camW: observerPositions[i],
                    satW: objectPositions[i],
                    sunW: sunPositions[i]);

                _csv.Add($"{timeStamp[i]},{adu.ToString(CultureInfo.InvariantCulture)}");
            }
            else
            {
                // Rendering
                var (lum, r, g, b) = RenderMeasureAndOptionallySave(i);

                 _csv.Add($"{timeStamp[i]},{lum.ToString(CultureInfo.InvariantCulture)}," +
                          $"{r.ToString(CultureInfo.InvariantCulture)}," +
                          $"{g.ToString(CultureInfo.InvariantCulture)}," +
                          $"{b.ToString(CultureInfo.InvariantCulture)}");
            }
            
            yield return null;
        }
        SaveLightCurveAndQuit();
    }
    #endregion

    #region === Rendering & Measurement =======================================================
    // Method to perform rendering, measure flux and save frames
    (float lum, float r, float g, float b) RenderMeasureAndOptionallySave(int frameIndex)
    {
        // 1) Rendering
        observer.targetTexture = _rtFull;
        observer.Render();
        observer.targetTexture = null;

        // 2) Copy to texture
        GL.Flush();
        ReadIntoTexture(_rtFull, _texFull, _fullRect);

        // 3) Set debug mode
        bool debugNow = DebugFirstFramePixels && !_debuggedPixels && frameIndex == 0;

        Colors m = ComputeColors(_texFull, frameIndex, debugNow ? Path.Combine(OutputFolder, PixelDebugFilename) : null);

        if (debugNow) _debuggedPixels = true;

        // 4) Optionally save full frame
        if (SaveFrames && frameIndex >= 0 && frameIndex < MaxFramesToSave)
        {
            if (SaveEXR) SaveFrameEXR(frameIndex);
            else SaveFramePNG(frameIndex);
        }
        if (SumFlux)
        {
            // Integrated flux
            return (m.sumY, m.sumR, m.sumG, m.sumB);
        }
        else
        {
            // Average across sampled pixels
            float invN = m.count > 0 ? 1f / m.count : 0f;
            return (m.sumY * invN, m.sumR * invN, m.sumG * invN, m.sumB * invN);
        }
    }

    // Method to copy rendering into a texture
    private void ReadIntoTexture(RenderTexture src, Texture2D dst, Rect rect)
    {
        RenderTexture prev = RenderTexture.active;
        RenderTexture.active = src;
        dst.ReadPixels(rect, 0, 0, false);
        dst.Apply(false, false);
        RenderTexture.active = prev;
    }

    // Method to compute color channels and luminance in linear space
    Colors ComputeColors(Texture2D tex,  int i, string debugPath = null)
    {
        // Init
        Vector3 integralTerm = new(1, 1, 1);
        double scaleTerm = 1.0;
        double gainTerm = 1.0;

        // Read HDR pixels (linear)
        NativeArray<Color> data = tex.GetRawTextureData<Color>();
        int n = data.Length;

        if (UseRadiometricModel)
        {
            //  Sun–object distance [km]
            double r_SO = sunRange[i];
            double r_OO = objectRange[i] * 1e3;
            if (r_SO < 1e-6) r_SO = 1e-6;

            // Compute ∫ Esun(λ)*sunScale * Tatm(λ) * TauTel(λ) * QE(λ) * (λ/hc) dλ electrons/m^2/s
            integralTerm = ComputeIntegralTerm(r_SO, eclipseFactor: 1.0);

            // Scale term
            double Omega = Math.PI / (4.0 * FNumber * FNumber);     // sr
            double Apx = Math.Pow(PixelSizeUM * 1e-6, 2.0);         // m^2
            double texp = ExposureSeconds;                          // s
            scaleTerm = Omega * Apx * texp / (r_OO * r_OO);

            // Set gain
            gainTerm = gain;
        }

        if (!string.IsNullOrEmpty(debugPath))
            DebugPixels(tex.width, tex.height, data, debugPath);

        // Loop on pixels: map geometry → electrons/pixel per band
        double sumR = 0, sumG = 0, sumB = 0;

        for (int ii = 0; ii < n; ii++)
        {
            var shaderTerm = data[ii];

            double eR = shaderTerm.r * integralTerm.x * scaleTerm * 1 / gainTerm;
            double eG = shaderTerm.g * integralTerm.y * scaleTerm * 1 / gainTerm;
            double eB = shaderTerm.b * integralTerm.z * scaleTerm * 1 / gainTerm;

            sumR += eR; sumG += eG; sumB += eB;
        }
        double Y = sumR + sumG + sumB;

        return new Colors
        {
            sumR = (float)sumR,
            sumG = (float)sumG,
            sumB = (float)sumB,
            sumY = (float)Y,
            count = n
        };
    }
    #endregion

    #region === Geometry, math & utils ========================================================
    // Set per-frame transforms
    private void SetGeometry(int i)
    {
        // World trajectories from CSV
        double3 satW = new double3(objectPositions[i].x, objectPositions[i].y, objectPositions[i].z);
        double3 camW = new double3(observerPositions[i].x, observerPositions[i].y, observerPositions[i].z);
        double3 sunW = new double3(sunPositions[i].x, sunPositions[i].y, sunPositions[i].z);

        double3 satRelD = satW - camW;
        double3 sunRelD = sunW - camW;

        // Place camera at origin
        Vector3 camRel = Vector3.zero;
        Vector3 satRel = new Vector3((float)satRelD.x, (float)satRelD.y, (float)satRelD.z);
        Vector3 sunRel = new Vector3((float)sunRelD.x, (float)sunRelD.y, (float)sunRelD.z);

        satellite.transform.SetPositionAndRotation(satRel, objectRotations[i]);

        observer.transform.position = camRel;
        observer.transform.rotation = Quaternion.LookRotation(satRel.normalized, Vector3.up);

        // Point directional light toward satellite
        Vector3 sunDir = (satRel - sunRel).normalized;
        sun.transform.rotation = Quaternion.LookRotation(sunDir, Vector3.up);

        _lastSatPosW = satellite.transform.position;
        _lastSunDirW = (sunRel - satRel).normalized;
    }
    private void ApplyUniformScale(float sceneScale)
    {
        if (sceneScale <= 0f) { Debug.LogWarning("ApplyUniformScale: sceneScale must be > 0"); return; }

        float s = sceneScale;

        // Scale input trajectories
        for (int i = 0; i < objectPositions.Count; i++)
        {
            objectPositions[i] /= s;
            observerPositions[i] /= s;
            sunPositions[i] /= s;
        }
        EnsureFixedClipPlanes();
    }

    // Method to push geometry from csv
    public void PushGeometry(List<Vector3> obj, List<Vector3> cam, List<Vector3> sunP, List<Quaternion> rot, List<string> time, List<float> objE, List<float> objR, List<float> sunR)
    {
        objectPositions = obj ?? new List<Vector3>();
        observerPositions = cam ?? new List<Vector3>();
        sunPositions = sunP ?? new List<Vector3>();
        objectRotations = rot ?? new List<Quaternion>();
        timeStamp = time ?? new List<string>();
        objectRange = objR ?? new List<float>();
        objectElevation = objE ?? new List<float>();
        sunRange = sunR ?? new List<float>();
    }
    // Method to load tabulated spectra in Curve struct
    private Curve LoadCsv(string path)
    {
        if (!File.Exists(path)) return new Curve { lam_nm = Array.Empty<float>(), y = Array.Empty<float>() };
        var lam = new List<float>();
        var val = new List<float>();
        foreach (string raw in File.ReadLines(path))
        {
            // Trim whitespaces
            string line = raw.Trim();
            // Check if data exists
            if (string.IsNullOrWhiteSpace(line) || line.StartsWith("#")) continue;
            string[] v = line.Split(',');
            lam.Add(ValuesParser(v[0]));
            val.Add(ValuesParser(v[1]));
        }
        return new Curve { lam_nm = lam.ToArray(), y = val.ToArray() };
    }

    // Method to compute the integral term in the radiometric model
    Vector3 ComputeIntegralTerm(double r_SunObj, double eclipseFactor = 1.0)
    {
        if (!_spectraReady)
            EnsureSpectra();
        double sunScale = eclipseFactor * Math.Pow(AU_KM / Math.Max(1e-3, r_SunObj), 2.0);

        float KR = (float)IntegrateBand_K(Rmin, Rmax, sunScale);
        float KG = (float)IntegrateBand_K(Gmin, Gmax, sunScale);
        float KB = (float)IntegrateBand_K(Bmin, Bmax, sunScale);

        return new Vector3(KR, KG, KB);
    }

    // Method to integrate (trapz) wavelength dependent quantities
    private double IntegrateBand_K(double lamMin_nm, double lamMax_nm, double sunScale)
    {
        double step = 1.0;
        int steps = Math.Max(1, (int)Math.Round((lamMax_nm - lamMin_nm) / step));
        double sum = 0.0;
        for (int k = 0; k < steps; k++)
        {
            double a_nm = lamMin_nm + k * step;
            double b_nm = (k == steps - 1) ? lamMax_nm : (a_nm + step);
            // sample ends
            double Ea = LerpAt(_Esun, a_nm) * sunScale; // Sun
            double Eb = LerpAt(_Esun, b_nm) * sunScale; // Sun
            double Ta = LerpAt(_Tatm, a_nm);            // Atmosphere
            double Tb = LerpAt(_Tatm, b_nm);            // Atmosphere
            double Xa = LerpAt(_WT, a_nm);              // Cam window
            double Xb = LerpAt(_WT, b_nm);              // Cam window
            double Qa = LerpAt(_QE, a_nm);              // QE window
            double Qb = LerpAt(_QE, b_nm);              // QE window

            // photons-per-joule factor λ/(hc) at endpoints
            double Pa = a_nm * 1e-9 / (H * C);
            double Pb = b_nm * 1e-9 / (H * C);

            double fa = Ea * Ta * Xa * Qa * Pa;
            double fb = Eb * Tb * Xb * Qb * Pb;

            // Trapz
            sum += 0.5 * (fa + fb) * (b_nm - a_nm);
        }
        // Electrons * m^-2 * s^-1
        return sum;
    }

    // Method to interpolate linearly at point nm
    private double LerpAt(in Curve c, double nm)
    {
        var x = c.lam_nm;
        var y = c.y;
        // Return 1 if either input is null or empty
        if (x == null || y == null || x.Length == 0 || y.Length == 0) return 1;
        int n = x.Length;
        float nmf = (float)nm;
        if (nm <= x[0]) return y[0];
        if (nm >= x[n - 1]) return y[n - 1];
        int i = Array.BinarySearch(x, nmf);
        if (i >= 0) return y[i];
        i = ~i;
        int i0 = i - 1, i1 = i;
        double t = (nmf - x[i0]) / (x[i1] - x[i0]);
        return y[i0] * (1 - t) + y[i1] * t;
    }
    float rayleighDepth(float P, float lambdaUM)
    {
        float P0 = 101325f;
        return  P / P0 * 0.00877f * Mathf.Pow(lambdaUM, -4.05f);
    }

    float ozoneExinction(float spacecraftElevation)
    {
        float ozoneExt = 1*0.016f;
        return Mathf.Pow(10.0f, ozoneExt / -2.5f);
    }
    float aerosolDepth(float tau0, float lambdaNM)
    {
        return tau0*Mathf.Pow(lambdaNM/550, -1.3f);
    }

    float airMass(float spacecraftElevation)
    {
        return  1f / (Mathf.Sin(spacecraftElevation/180f*3.141592f) + 0.50572f*Mathf.Pow(6.07995f + spacecraftElevation, -1.6364f));
    }

    // Method to the debug pixel encoding (save pixels on output file before encoding)
    private void DebugPixels(int width, int height, NativeArray<Color> data, string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path) ?? ".");

        // Stream out to avoid huge string allocations
        using var sw = new StreamWriter(path, false, Encoding.UTF8, bufferSize: 1 << 20);
        // Header
        sw.WriteLine("i,x,y,R,G,B,A,Y");

        // Use round-trip format for floats
        var inv = CultureInfo.InvariantCulture;

        for (int i = 0; i < data.Length; i++)
        {
            int x = i % width;
            int y = i / width;
            var c = data[i];

            double Y = c.r + c.g + c.b;

            sw.Write(i); sw.Write(',');
            sw.Write(x); sw.Write(',');
            sw.Write(y); sw.Write(',');
            sw.Write(c.r.ToString("R", inv)); sw.Write(',');
            sw.Write(c.g.ToString("R", inv)); sw.Write(',');
            sw.Write(c.b.ToString("R", inv)); sw.Write(',');
            sw.Write(c.a.ToString("R", inv)); sw.Write(',');
            sw.WriteLine(Y.ToString("R", inv));
        }
    }

    // Method to parse string values
    private float ValuesParser(string s) => float.Parse(s, CultureInfo.InvariantCulture);
    #endregion

    #region === I/O ===========================================================================

    // Method to save frames in PNG format with optional axis drawing
    private void SaveFramePNG(int frameIndex, int exposure = 1, float gamma = 2.2f, float scale = 1.0f)
    {
        
        int OverlayThickness   = 4;
        int WorldAxisThickness = Mathf.Max(1, OverlayThickness / 2);
        int AxisPixels         = 240;
        Color32 sColor = new Color32(255, 255, 255, 255);
        Color32 xColor = new Color32(255, 0, 0, 255);
        Color32 yColor = new Color32(0, 255, 0, 255);
        Color32 zColor = new Color32(0, 0, 255, 255);

        int w = Mathf.Max(1, Mathf.RoundToInt(CaptureWidth  * Mathf.Clamp01(scale)));
        int h = Mathf.Max(1, Mathf.RoundToInt(CaptureHeight * Mathf.Clamp01(scale)));

        var rtDown = RenderTexture.GetTemporary(w, h, 0, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
        try
        {
            Graphics.Blit(_rtFull, rtDown);

            var texHDR = new Texture2D(
                w, h,
                SystemInfo.SupportsTextureFormat(TextureFormat.RGBAFloat) ? TextureFormat.RGBAFloat : TextureFormat.RGBAHalf,
                mipChain: false, linear: true);

            var prev = RenderTexture.active;
            RenderTexture.active = rtDown;
            texHDR.ReadPixels(new Rect(0, 0, w, h), 0, 0, false);
            texHDR.Apply(false, false);
            RenderTexture.active = prev;

            var src = texHDR.GetRawTextureData<Color>();
            var dst = new Color32[src.Length];

            float invGamma = 1f / gamma;
            for (int i = 0; i < src.Length; i++)
            {
                float r = Mathf.Max(0f, src[i].r * exposure);
                float g = Mathf.Max(0f, src[i].g * exposure);
                float b = Mathf.Max(0f, src[i].b * exposure);

                // gamma to ~sRGB
                r = Mathf.Pow(r, invGamma);
                g = Mathf.Pow(g, invGamma);
                b = Mathf.Pow(b, invGamma);

                // clamp & pack
                dst[i] = new Color32(
                    (byte)Mathf.Clamp(Mathf.RoundToInt(r * 255f), 0, 255),
                    (byte)Mathf.Clamp(Mathf.RoundToInt(g * 255f), 0, 255),
                    (byte)Mathf.Clamp(Mathf.RoundToInt(b * 255f), 0, 255),
                    255);
            }

            if (DrawAxis)
            {
                // Helper: take a world vector and transform it in the viewport space, adapted to camera resolution
                Vector2 P(Vector3 wp) { var v = observer.WorldToViewportPoint(wp); return new Vector2(v.x * w, v.y * h); }

                // Helper: how many world units for given pixels
                float WorldLenForPixels(Vector3 originW, Vector3 axisDirW, float pixels)
                {
                    if (axisDirW.sqrMagnitude < 1e-12f) return 0f;
                    var p0s = observer.WorldToScreenPoint(originW);
                    var p1s = observer.WorldToScreenPoint(originW + axisDirW.normalized);
                    float pixPerUnit = Vector2.Distance(new Vector2(p0s.x, p0s.y), new Vector2(p1s.x, p1s.y));
                    if (pixPerUnit <= 1e-6f) return 0f;
                    return pixels / pixPerUnit;
                }

                // Helper: draw RGB line to buf from p0 to p1 with thickness t and color c
                void DrawLineRGBA32(Color32[] buf, int bw, int bh, Vector2 p0, Vector2 p1, Color32 c, int t)
                {
                    int x0 = Mathf.RoundToInt(p0.x), y0 = Mathf.RoundToInt(p0.y);
                    int x1 = Mathf.RoundToInt(p1.x), y1 = Mathf.RoundToInt(p1.y);
                    int dx = Mathf.Abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
                    int dy = -Mathf.Abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
                    int err = dx + dy;

                    // Helper: assign thickness to the line
                    void BlitThickRGBA32(int x, int y, Color32 col, int thick)
                    {
                        int r = Mathf.Max(1, thick / 2);
                        for (int yy = y - r; yy <= y + r; yy++)
                            for (int xx = x - r; xx <= x + r; xx++)
                            {
                                if ((uint)xx >= (uint)bw || (uint)yy >= (uint)bh) continue;
                                buf[yy * bw + xx] = col;
                            }
                    }

                    while (true)
                    {
                        BlitThickRGBA32(x0, y0, c, t);
                        if (x0 == x1 && y0 == y1) break;
                        int e2 = 2 * err;
                        if (e2 >= dy) { err += dy; x0 += sx; }
                        if (e2 <= dx) { err += dx; y0 += sy; }
                    }
                }

                // Helper: draw world axis dirW on png
                void DrawAxisSat(Vector3 originW, Vector3 dirW, Color32 col, int t)
                {
                    if (dirW.sqrMagnitude < 1e-11f) return;
                    
                    float Lw = WorldLenForPixels(originW, dirW, AxisPixels);
                    Vector3 p1w = originW + dirW.normalized * Lw;

                    var v0 = observer.WorldToViewportPoint(originW);
                    var v1 = observer.WorldToViewportPoint(p1w);
                    if (v0.z <= 0f || v1.z <= 0f) return;

                    DrawLineRGBA32(dst, w, h, P(originW), P(p1w), col, t);
                }

                // Skip if satellite behind camera
                var vSat = observer.WorldToViewportPoint(_lastSatPosW);
                if (vSat.z > 0f)
                {
                    // Sun
                    DrawAxisSat(_lastSatPosW, _lastSunDirW, sColor, OverlayThickness);
                    // Object
                    DrawAxisSat(_lastSatPosW, satellite.transform.right,   xColor, OverlayThickness);
                    DrawAxisSat(_lastSatPosW, satellite.transform.up,      yColor, OverlayThickness);
                    DrawAxisSat(_lastSatPosW, satellite.transform.forward, zColor, OverlayThickness);
                }
            }

            // Upload pixels and save
            var outTex = new Texture2D(w, h, TextureFormat.RGBA32, mipChain: false, linear: false);
            outTex.SetPixelData(dst, 0);
            outTex.Apply(false, false);

            string file = Path.Combine(OutputFolder, $"frame_{frameIndex:D04}.png");
            File.WriteAllBytes(file, outTex.EncodeToPNG());

            Destroy(texHDR);
            Destroy(outTex);
        }
        finally
        {
            RenderTexture.ReleaseTemporary(rtDown);
        }
    }

    // Method to save frames in EXR format (raw)
    private void SaveFrameEXR(int count)
    {
        string file = Path.Combine(OutputFolder, $"frame_{count:D04}.exr");
        File.WriteAllBytes(file, _texFull.EncodeToEXR(Texture2D.EXRFlags.None));
    }

    // Method to save light curve generated in current instance
    private void SaveLightCurveAndQuit()
    {
        string filename = LightCurveFilename;
        File.WriteAllLines(filename, _csv);
        Debug.Log($"Light curve saved: {filename}");
#if UNITY_EDITOR
        UnityEditor.EditorApplication.isPlaying = false;
#else
        Application.Quit();
#endif
    }
    #endregion

    #region === Camera, lighting & RT setup ===================================================
    // Method to configure light environment
    private void ConfigureSun()
    {
        // One light only (the sun)
        foreach (var l in FindObjectsByType<Light>(FindObjectsSortMode.None))
            if (l != sun) Destroy(l.gameObject);

        RenderSettings.ambientMode = AmbientMode.Flat;
        RenderSettings.ambientLight = Color.black;
        RenderSettings.skybox = null;
        RenderSettings.defaultReflectionMode = DefaultReflectionMode.Custom;
        RenderSettings.customReflectionTexture = null;
        RenderSettings.fog = false;
        // Delete eventual probes
        foreach (var r in FindObjectsByType<Renderer>(FindObjectsSortMode.None))
        {
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r.lightProbeUsage = LightProbeUsage.Off;
        }
        // Set sun
        sun.type = LightType.Directional;
        sun.shadows = ShadowCast ? LightShadows.Hard : LightShadows.None;
        sun.shadowStrength = 1f;
        sun.shadowBias = 0.10f;
        sun.shadowNormalBias = 0.60f;
        sun.shadowNearPlane = 0.20f;
    }

    // Method to configure observer environment
    private void ConfigureCamera()
    {

        if (useOrtographic)
        {
            observer.orthographic = true;
            observer.orthographicSize = camSize;
            Debug.Log($"{observer.orthographic} and {observer.orthographicSize}");
        }
        else
        {
            observer.orthographic = false;
            observer.usePhysicalProperties = true;

            // Set physical properties
            observer.focalLength = FL;                          
            observer.sensorSize = new Vector2(sensorSize, sensorSize);    
            observer.lensShift  = Vector2.zero;         
        }
        
        var camData = observer.GetUniversalAdditionalCameraData();

        // Set observer
        observer.allowHDR = true;
        observer.clearFlags = CameraClearFlags.SolidColor;
        observer.backgroundColor = Color.black;
        observer.useOcclusionCulling = false;
        if (camData != null)
        {
            camData.cameraStack.Clear();
            camData.renderType = CameraRenderType.Base;
            camData.renderPostProcessing = false;
            camData.dithering = false;
            camData.allowHDROutput = false;
            camData.requiresDepthTexture = true;
            camData.renderShadows = ShadowCast;
        }

        QualitySettings.antiAliasing = 0;

        if (!EnableView) observer.enabled = false;
        // Check linearity
        if (!_projectLinear)
            Debug.LogWarning("Project color space is Gamma. For physical photometry prefer Linear in Project Settings.");
    }

    // Method to initialize rendering targets
    private void EnsureRenderTargets()
    {
        // FULL RT (for saving frames)
        CreateOrResizeRT(ref _rtFull, CaptureWidth, CaptureHeight, RenderTextureFormat.ARGBHalf);
        CreateOrResizeTex(ref _texFull, CaptureWidth, CaptureHeight, TextureFormat.RGBAHalf);

        _fullRect = new Rect(0, 0, CaptureWidth, CaptureHeight);
    }

    // Method to initialize render texture
    private void CreateOrResizeRT(ref RenderTexture rt, int w, int h, RenderTextureFormat fmt)
    {
        if (rt != null && (rt.width != w || rt.height != h || rt.format != fmt))
        {
            rt.Release();
            rt = null!;
        }
        if (rt == null)
        {
            rt = new RenderTexture(w, h, 24, SystemInfo.SupportsRenderTextureFormat(fmt) ? fmt : RenderTextureFormat.ARGB32)
            {
                antiAliasing = 1,
                useMipMap = false,
                autoGenerateMips = false,
                enableRandomWrite = false,
            };
            rt.Create();
        }
    }
    // Method to initialize texture2D
    private void CreateOrResizeTex(ref Texture2D t, int w, int h, TextureFormat fmt)
    {
        // Match texture format to RT choice (fallback if unsupported)
        if (!SystemInfo.SupportsTextureFormat(fmt))
            fmt = TextureFormat.RGBA32;

        // Prefer float when available
        if (SystemInfo.SupportsTextureFormat(TextureFormat.RGBAFloat))
            fmt = TextureFormat.RGBAFloat;

        bool linear = true;

        if (!t || t.width != w || t.height != h || t.format != fmt)
        {
            if (t) Destroy(t);
            t = new Texture2D(w, h, fmt, mipChain: false, linear: linear);
        }
    }
    // Method to release RT resources
    private void ReleaseRT(ref RenderTexture rt)
    {
        if (rt != null)
        {
            rt.Release();
            rt = null!;
        }
    }
    // Method to compute fixed clip planes once geometry is known
    private void EnsureFixedClipPlanes()
    {
        if (_clipInitialized) return;
        if (objectPositions.Count == 0 || observerPositions.Count == 0) return;

        ComputeFixedClipPlanes();

        observer.nearClipPlane = _nearFixed;
        observer.farClipPlane = _farFixed;

        // Set a constant shadow distance to avoid per-frame changes
        var urp = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
        if (urp != null)
            urp.shadowDistance = _farFixed + 2.0f;
    }

    // Method to compute fixed clip planes from min/max camera–target distances
    private void ComputeFixedClipPlanes()
    {
        int n = Mathf.Min(objectPositions.Count, observerPositions.Count);
        if (n == 0) return;

        float minD = float.PositiveInfinity;
        float maxD = 0f;
        // Find min and max target distance from observer
        for (int i = 0; i < n; i++)
        {
            float d = (objectPositions[i] - observerPositions[i]).magnitude;
            if (d < minD) minD = d;
            if (d > maxD) maxD = d;
        }
        Debug.Log($"{minD}, {maxD}");
        // Conservative bounding radius of the satellite (world space)
        Bounds b = new Bounds(satellite.transform.position, Vector3.zero);
        foreach (var r in satellite.GetComponentsInChildren<Renderer>(true))
            b.Encapsulate(r.bounds);
        float radius = b.extents.magnitude;

        const float margin = 2f;
        float near = Mathf.Max(kMinNearClip, minD - radius - margin);
        float far = Mathf.Max(near + kMinClipSpan, maxD + radius + margin);

        _nearFixed = near;
        _farFixed = far;
        _clipInitialized = true;

        Debug.Log($"[Clipping] Fixed planes set: near={_nearFixed:F3} m, far={_farFixed:F3} m " +
                  $"(minD={minD:F3}, maxD={maxD:F3}, r={radius:F3}, margin={margin:F3}).");
    }
    // Method to load tabulated spectra (csv)
    private void EnsureSpectra()
    {
        // Load Sun
        _Esun = LoadCsv(SunSpectrumCSV);
        // Load camera QE
        _QE   = LoadCsv(QECSV);
        // Load telescope efficiency
        _WT   = LoadCsv(WTCSV);
        // Set to true
        _spectraReady = true;
    }
    #endregion
}