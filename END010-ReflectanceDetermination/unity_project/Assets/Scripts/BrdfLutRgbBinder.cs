using System;
using UnityEngine;

public class BrdfLutRgbBinder : MonoBehaviour
{
    [Serializable]
    private class Meta
    {
        public int nAzL, nThL, nAzC, nThC;
        public float azMinL, thMinL, azMinC, thMinC;
        public float azStepL, thStepL, azStepC, thStepC;
        public string units;
        public int[] bandRGB;
    }

    [Header("Inputs")]
    public TextAsset lutBin;     // rename lut.bin -> lut.bytes in Unity, then drag here
    public TextAsset lutJson;    // drag lut.json here

    [Header("Bind target")]
    [Tooltip("Assign the plate/sphere Renderer here. We'll bind to Renderer.material to avoid material instance mismatch.")]
    public Renderer targetRenderer;

    private ComputeBuffer _lutBuffer;

    void Start()
    {
        if (lutBin == null || lutJson == null || targetRenderer == null)
        {
            Debug.LogError("Assign lutBin, lutJson, and targetRenderer in the Inspector.");
            return;
        }

        // Parse JSON
        var meta = JsonUtility.FromJson<Meta>(lutJson.text);
        if (meta == null)
        {
            Debug.LogError("Failed to parse LUT JSON.");
            return;
        }

        int count = meta.nAzL * meta.nThL * meta.nAzC * meta.nThC;
        if (count <= 0)
        {
            Debug.LogError($"Invalid LUT dimensions from JSON: nAzL={meta.nAzL}, nThL={meta.nThL}, nAzC={meta.nAzC}, nThC={meta.nThC}");
            return;
        }

        // float4 per point => 16 bytes
        _lutBuffer = new ComputeBuffer(count, sizeof(float) * 4, ComputeBufferType.Structured);

        // Read floats from bytes
        byte[] bytes = lutBin.bytes;
        int floatsExpected = count * 4;

        if (bytes.Length < floatsExpected * sizeof(float))
        {
            Debug.LogWarning($"LUT file is smaller than expected. expectedBytes={floatsExpected * sizeof(float)}, gotBytes={bytes.Length}");
        }

        float[] f = new float[floatsExpected];
        Buffer.BlockCopy(bytes, 0, f, 0, Mathf.Min(bytes.Length, floatsExpected * sizeof(float)));

        Debug.Log($"LUT points={count}, expected bytes={count * 16}, got bytes={bytes.Length}");

        // Convert to Vector4[] and compute stats
        Vector4[] v = new Vector4[count];

        double minR = double.PositiveInfinity, minG = double.PositiveInfinity, minB = double.PositiveInfinity;
        double maxR = double.NegativeInfinity, maxG = double.NegativeInfinity, maxB = double.NegativeInfinity;
        double sumR = 0, sumG = 0, sumB = 0;

        for (int i = 0; i < count; i++)
        {
            int o = i * 4;
            float r = f[o + 0];
            float g = f[o + 1];
            float b = f[o + 2];
            float a = f[o + 3];

            v[i] = new Vector4(r, g, b, a);

            minR = Math.Min(minR, r); minG = Math.Min(minG, g); minB = Math.Min(minB, b);
            maxR = Math.Max(maxR, r); maxG = Math.Max(maxG, g); maxB = Math.Max(maxB, b);
            sumR += r; sumG += g; sumB += b;
        }

        double inv = 1.0 / count;
        Debug.Log($"LUT RGB stats: " +
                  $"R[min={minR:F6}, max={maxR:F6}, mean={sumR * inv:F6}]  " +
                  $"G[min={minG:F6}, max={maxG:F6}, mean={sumG * inv:F6}]  " +
                  $"B[min={minB:F6}, max={maxB:F6}, mean={sumB * inv:F6}]");

        // Upload
        _lutBuffer.SetData(v);

        // Bind to the *actual* material instance used by the renderer
        Material mat = targetRenderer.material;

        mat.SetBuffer("_BrdfLutRgb", _lutBuffer);

        mat.SetInt("_nAzL", meta.nAzL);
        mat.SetInt("_nThL", meta.nThL);
        mat.SetInt("_nAzC", meta.nAzC);
        mat.SetInt("_nThC", meta.nThC);

        mat.SetFloat("_azMinL", meta.azMinL);
        mat.SetFloat("_thMinL", meta.thMinL);
        mat.SetFloat("_azMinC", meta.azMinC);
        mat.SetFloat("_thMinC", meta.thMinC);

        mat.SetFloat("_azStepL", meta.azStepL);
        mat.SetFloat("_thStepL", meta.thStepL);
        mat.SetFloat("_azStepC", meta.azStepC);
        mat.SetFloat("_thStepC", meta.thStepC);
    }

    void OnDestroy()
    {
        if (_lutBuffer != null)
        {
            _lutBuffer.Release();
            _lutBuffer = null;
        }
    }
}
