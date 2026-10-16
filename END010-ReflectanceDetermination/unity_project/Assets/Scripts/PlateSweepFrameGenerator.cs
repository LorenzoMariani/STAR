using System;
using System.Globalization;
using System.IO;
using UnityEngine;

public class PlateSweepFrameGenerator : MonoBehaviour
{
    [Header("Scene refs")]
    public Transform plate;      // your flat plate (quad/plane)
    public Light sun;            // directional light
    public Camera observer;      // capture camera
    public BrdfLutRgbBinder lutBinder; // optional: just to ensure binder exists

    [Header("Fixed light direction (world)")]
    [Tooltip("Light azimuth around +Y, reference +X (deg).")]
    public float sunAzDeg = 120f;
    [Tooltip("Light colatitude from +Y (deg). 0=from above, 90=horizontal.")]
    public float sunColatDeg = 40f;

    [Header("Camera sweep (world)")]
    public int numFrames = 360;
    public float xStart = -2f;
    public float xEnd   =  2f;
    public float camY   =  0.5f;
    public float camZ   = -3f;
    public Vector3 lookAtOffset = Vector3.zero;

    [Header("Capture")]
    public int width = 512;
    public int height = 512;
    public bool saveFrames = true;
    public bool saveEXR = false;
    public float pngExposure = 1f;
    public float pngGamma = 2.2f;
    public string outputFolder = "Frames_PlateSweep";
    public string csvName = "plate_sweep.csv";

    RenderTexture _rt;
    Texture2D _texFloat;

    void Start()
    {
        if (!plate || !sun || !observer)
        {
            Debug.LogError("Assign plate, sun, observer.");
            return;
        }
        StartCoroutine(Run());
    }

    System.Collections.IEnumerator Run()
    {
        // Wait 1 frame so BrdfLutRgbBinder.Start() uploads LUT
        yield return null;

        // Fixed sun direction
        Vector3 L = SphericalDirDeg(sunAzDeg, sunColatDeg); // direction from point -> light
        sun.type = LightType.Directional;
        // Directional light rays go along light.forward, so set forward = -L
        sun.transform.rotation = Quaternion.LookRotation(L, Vector3.up);

        // Setup output
        string outDir = Path.Combine(Application.dataPath, "../" + outputFolder);
        Directory.CreateDirectory(outDir);
        string csvPath = Path.Combine(outDir, csvName);

        // RT + float texture
        _rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGBHalf);
        _rt.Create();
        _texFloat = new Texture2D(width, height, TextureFormat.RGBAFloat, false, true);

        using var sw = new StreamWriter(csvPath);
        sw.WriteLine("frame,cameraX,meanR,meanG,meanB,meanY");

        for (int i = 0; i < numFrames; i++)
        {
            float t = (numFrames <= 1) ? 0f : (float)i / (numFrames - 1);
            float camX = Mathf.Lerp(xStart, xEnd, t);

            observer.transform.position = new Vector3(camX, camY, camZ);
            observer.transform.LookAt(plate.position + lookAtOffset, Vector3.up);

            // Render
            observer.targetTexture = _rt;
            observer.Render();
            observer.targetTexture = null;

            // Read
            RenderTexture prev = RenderTexture.active;
            RenderTexture.active = _rt;
            _texFloat.ReadPixels(new Rect(0, 0, width, height), 0, 0, false);
            _texFloat.Apply(false, false);
            RenderTexture.active = prev;

            // Measure means in linear space
            (float r, float g, float b) = MeanRGB(_texFloat);
            float y = r + g + b;

            sw.WriteLine($"{i},{camX.ToString("R",CultureInfo.InvariantCulture)}," +
                         $"{r.ToString("R",CultureInfo.InvariantCulture)}," +
                         $"{g.ToString("R",CultureInfo.InvariantCulture)}," +
                         $"{b.ToString("R",CultureInfo.InvariantCulture)}," +
                         $"{y.ToString("R",CultureInfo.InvariantCulture)}");

            if (saveFrames)
            {
                if (saveEXR)
                {
                    File.WriteAllBytes(Path.Combine(outDir, $"frame_{i:D04}.exr"),
                        _texFloat.EncodeToEXR(Texture2D.EXRFlags.None));
                }
                else
                {
                    SavePNG_Tonemapped(_texFloat, Path.Combine(outDir, $"frame_{i:D04}.png"), pngExposure, pngGamma);
                }
            }

            yield return null;
        }

        Debug.Log($"Done. Wrote frames + CSV to: {outDir}");

#if UNITY_EDITOR
        UnityEditor.EditorApplication.isPlaying = false;
#else
        Application.Quit();
#endif
    }

    static Vector3 SphericalDirDeg(float azDeg, float colatDeg)
    {
        float az = azDeg * Mathf.Deg2Rad;
        float th = colatDeg * Mathf.Deg2Rad;
        float sinT = Mathf.Sin(th);
        float x = sinT * Mathf.Cos(az);
        float z = sinT * Mathf.Sin(az);
        float y = Mathf.Cos(th);
        return new Vector3(x, y, z).normalized;
    }

    static (float r, float g, float b) MeanRGB(Texture2D tex)
    {
        var data = tex.GetRawTextureData<Color>();
        double sr = 0, sg = 0, sb = 0;
        int n = data.Length;

        for (int i = 0; i < n; i++)
        {
            var c = data[i];
            sr += c.r; sg += c.g; sb += c.b;
        }
        float inv = (n > 0) ? (float)(1.0 / n) : 0f;
        return ((float)sr * inv, (float)sg * inv, (float)sb * inv);
    }

    static void SavePNG_Tonemapped(Texture2D texFloat, string path, float exposure, float gamma)
    {
        int w = texFloat.width, h = texFloat.height;
        var src = texFloat.GetRawTextureData<Color>();
        var dst = new Color32[src.Length];

        float invGamma = 1f / Mathf.Max(1e-6f, gamma);

        for (int i = 0; i < src.Length; i++)
        {
            float r = Mathf.Max(0f, src[i].r * exposure);
            float g = Mathf.Max(0f, src[i].g * exposure);
            float b = Mathf.Max(0f, src[i].b * exposure);

            r = Mathf.Pow(r, invGamma);
            g = Mathf.Pow(g, invGamma);
            b = Mathf.Pow(b, invGamma);

            dst[i] = new Color32(
                (byte)Mathf.Clamp(Mathf.RoundToInt(r * 255f), 0, 255),
                (byte)Mathf.Clamp(Mathf.RoundToInt(g * 255f), 0, 255),
                (byte)Mathf.Clamp(Mathf.RoundToInt(b * 255f), 0, 255),
                255);
        }

        var outTex = new Texture2D(w, h, TextureFormat.RGBA32, false, false);
        outTex.SetPixelData(dst, 0);
        outTex.Apply(false, false);

        File.WriteAllBytes(path, outTex.EncodeToPNG());
        UnityEngine.Object.Destroy(outTex);
    }

    void OnDestroy()
    {
        if (_rt != null) { _rt.Release(); _rt = null; }
        if (_texFloat != null) Destroy(_texFloat);
    }
}