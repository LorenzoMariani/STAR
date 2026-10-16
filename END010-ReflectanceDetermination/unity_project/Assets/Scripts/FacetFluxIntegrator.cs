using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;

[DefaultExecutionOrder(-50)]
public class FacetFluxIntegrator : MonoBehaviour
{
    #region === Inspector references ==========================================================

    [Header("Visibility & Shadowing")]
    [Tooltip("Layer mask containing the satellite colliders for raycasts.")]
    public LayerMask SatelliteLayerMask = ~0;

    public LightCurveGenerator Source;

    [Header("Three-band integration (nm)")]
    [Tooltip("Band 1 [nm], e.g., Blue 425-500")]
    public Vector2 Band1NM = new Vector2(425f, 500f);
    [Tooltip("Band 2 [nm], e.g., Gree 500-580")]
    public Vector2 Band2NM = new Vector2(500f, 580f);
    [Tooltip("Band 3 [nm], e.g., Red 580-702.5")]
    public Vector2 Band3NM = new Vector2(580f, 702.5f);
    #endregion

    #region === Internal buffers ==============================================================    
    
    struct Curve { public float[] lam_nm; public float[] y; }
    Curve _Esun, _QE, _WT, _Tatm;
    bool _spectraReady;

    private readonly List<Part> _parts = new();
    // Per-mesh cached data
    private sealed class Part
    {
        public MeshFilter mf;
        public MeshCollider col;
        public Mesh mesh;
        public Matrix4x4 localToWorld;
        public Vector3[] verts;
        public int subMeshCount;
        public int[] submeshTriOffset;
        public Material[] materials;
    }
    private float RaycastEpsKM = 1e-4f;
    private readonly float steps = 1f;

    // Constants
    const double H = 6.62607015e-34;            // Planck [J·s]
    const double C = 2.99792458e8;              // light speed [m/s]
    const double AU_KM = 149_597_870.700;       // [km]

    public double LastSunObjectDistance_km { get; private set; }

    // Last per-band results
    public double LastBand1 { get; private set; }
    public double LastBand2 { get; private set; }
    public double LastBand3 { get; private set; }
    #endregion

    #region === Lifecycle =====================================================================
    void Awake()
    {
        if (!Source)
        {
            Debug.LogError("FacetFluxIntegrator: assign Source (LightCurveGenerator).");
            enabled = false; return;
        }
        if (!Source.satellite || !Source.observer || !Source.sun)
        {
            Debug.LogError("FacetFluxIntegrator: assign Satellite, Observer, and Sun.");
            enabled = false; return;
        }
        BuildPartsCache();
        EnsureSpectraFromSource();
    }

    void OnValidate()
    {
        RaycastEpsKM = Mathf.Max(1e-6f, RaycastEpsKM);
        if (Band1NM.y < Band1NM.x) (Band1NM.x, Band1NM.y) = (Band1NM.y, Band1NM.x);
        if (Band2NM.y < Band2NM.x) (Band2NM.x, Band2NM.y) = (Band2NM.y, Band2NM.x);
        if (Band3NM.y < Band3NM.x) (Band3NM.x, Band3NM.y) = (Band3NM.y, Band3NM.x);

    }
    #endregion

    #region === Compute flux ==================================================================
    public (double electrons, double adu) ComputeFrameFlux(Vector3 camW, Vector3 satW, Vector3 sunW)
    {
        var observer = Source.observer;
        var sun = Source.sun;
        // Keep transforms numerically stable: put cam at origin, shift others relative
        Vector3 camRel = Vector3.zero;
        Vector3 satRel = satW - camW;
        Vector3 sunRel = sunW - camW;
        // Observer
        observer.transform.position = camRel;
        observer.transform.rotation = Quaternion.LookRotation((satRel - camRel).normalized, Vector3.up);
        // Sun
        Vector3 sunDir = (satRel - sunRel).normalized;
        sun.transform.rotation = Quaternion.LookRotation(sunDir, Vector3.up);
        sun.transform.position = sunRel.normalized;

        // Update per-part transforms (in case the satellite is rotating this frame)
        foreach (var p in _parts)
            p.localToWorld = p.mf.transform.localToWorldMatrix;
        EnsureSpectraFromSource();
    
        // Radiometric integral: electrons / (m^2·s) at the object surface
        LastSunObjectDistance_km = Math.Max(1e-6, (sunW - satW).magnitude);
        double K1 = IntegrateElectronsPerAreaPerSecondBand(LastSunObjectDistance_km, Band1NM.x, Band1NM.y);
        double K2 = IntegrateElectronsPerAreaPerSecondBand(LastSunObjectDistance_km, Band2NM.x, Band2NM.y);
        double K3 = IntegrateElectronsPerAreaPerSecondBand(LastSunObjectDistance_km, Band3NM.x, Band3NM.y);

        // Aperture area and exposure
        double A_pupil = Math.PI * 0.25 * Source.Dm * Source.Dm;
        double texp = Math.Max(0.0, Source.ExposureSeconds);
        double sum1 = 0.0, sum2 = 0.0, sum3 = 0.0;

        // Loop on cached parts (meshes)
        foreach (var p in _parts)
        {
            var mesh = p.mesh;
            if (!mesh) continue;

            var mr = p.mf.GetComponent<MeshRenderer>();
            var mats = mr ? mr.sharedMaterials : null;
            // Loop on submeshes
            for (int s = 0; s < p.subMeshCount; s++)
            {
                // Get triangles belonging to each submesh
                var tris = mesh.GetTriangles(s);
                // Get submesh material
                var mat = (mats != null && s < mats.Length) ? mats[s] : null;
                // Get material BRDF parameters
                BRDFParams brdf = GetBRDFParams(mat);
                // Number of triangles
                int triCount = tris.Length / 3;
                int triBase = p.submeshTriOffset[s];
                // Loop on submesh triangles
                for (int t = 0; t < triCount; t++)
                {
                    int triGlobal = triBase + t;

                    int i0 = tris[3 * t + 0];
                    int i1 = tris[3 * t + 1];
                    int i2 = tris[3 * t + 2];

                    // World space vertex in km
                    Vector3 v0 = p.localToWorld.MultiplyPoint3x4(p.verts[i0]);
                    Vector3 v1 = p.localToWorld.MultiplyPoint3x4(p.verts[i1]);
                    Vector3 v2 = p.localToWorld.MultiplyPoint3x4(p.verts[i2]);
                    // Facet area in km^2
                    Vector3 e1 = v1 - v0;
                    Vector3 e2 = v2 - v0;
                    Vector3 n  = Vector3.Cross(e1, e2);
                    float doubleArea_km2 = n.magnitude * 0.001f;
                    if (doubleArea_km2 <= 1e-12f) continue;
                    // Facet normal
                    Vector3 Nn = Vector3.Normalize(n);
                    // Facet centroid
                    Vector3 centroid = (v0 + v1 + v2) / 3f;
                    // View unit vector
                    Vector3 Vdir = (observer.transform.position - centroid).normalized;
                    // Light unit vector
                    Vector3 Ldir = (sun.transform.position - centroid).normalized;
                    // Dot products
                    float NdotV = Mathf.Max(0f, Vector3.Dot(Nn, Vdir));
                    float NdotL = Mathf.Max(0f, Vector3.Dot(Nn, Ldir));

                    // Skip if facet non visible or not illuminated
                    if (NdotV <= 0f || NdotL <= 0f) continue;

                    // Visibility to camera
                    if (!VisibleFromCamera(p.col, triGlobal, centroid))
                        continue;

                    // Self-shadow toward sun
                    if (SelfShadowed(p.col, triGlobal, centroid, Ldir))
                        continue;

                    // Facet area in m^2
                    double A_tri_m2 = 0.5 * doubleArea_km2 * 1e6;
                    // Range camera–centroid [m]
                    double r_cam_m = (observer.transform.position - centroid).magnitude * 1000.0;
                    if (r_cam_m <= 1e-3) continue;
                    // Compute facet BRDF
                    var (frR, frG, frB) = EvaluateBRDF(brdf, Nn, Vdir, Ldir);
                    // compute geometry
                    double geomR = NdotL * frR * NdotV * A_tri_m2 / (r_cam_m * r_cam_m);
                    double geomG = NdotL * frG * NdotV * A_tri_m2 / (r_cam_m * r_cam_m);
                    double geomB = NdotL * frB * NdotV * A_tri_m2 / (r_cam_m * r_cam_m);
                    // Facet flux
                    sum1 += K1 * texp * A_pupil * geomR;
                    sum2 += K2 * texp * A_pupil * geomG;
                    sum3 += K3 * texp * A_pupil * geomB;
                }
            }
        }
        

        LastBand1 = sum1;
        LastBand2 = sum2;
        LastBand3 = sum3;

        double electrons = sum1 + sum2 + sum3;
        double ePerADU = Math.Max(1e-12, Source.gain);
        double adu = electrons / ePerADU;
        return (electrons, adu);
    }
    #endregion

    #region === Helpers =======================================================================
    // Method to check if facet is visible from camera through raycasting
    private bool VisibleFromCamera(MeshCollider col, int triGlobalIndex, Vector3 pointWS)
    {
        // Ray from camera toward the point
        Vector3 origin = Source.observer.transform.position;
        Vector3 dir = pointWS - origin;
        float dist = dir.magnitude;
        if (dist < 1e-6f) return false;
        dir /= dist;

        Vector3 start = origin + dir * RaycastEpsKM;
        float maxDist = Mathf.Max(0f, dist - 2f * RaycastEpsKM);

        if (Physics.Raycast(start, dir, out var hit, maxDist, SatelliteLayerMask, QueryTriggerInteraction.Ignore))
        {
            // The front-most hit must be THIS collider and THIS triangle
            return hit.collider == col && hit.triangleIndex == triGlobalIndex;
        }
        // If nothing hit, point is not blocked by satellite
        return true;
    }
    // Method to check if facet is shadowed through raycasting
    private bool SelfShadowed(MeshCollider col, int triGlobalIndex, Vector3 pointWS, Vector3 Ldir)
    {
        // Cast a ray from the point toward the sun (opposite of incoming light is -Ldir)
        Vector3 dir = -Ldir.normalized;
        Vector3 start = pointWS + dir * RaycastEpsKM;

        // Limit to a few satellite radii
        float maxDist = EstimateSatelliteRadiusKM() * 4f + 1f;
        if (maxDist <= 0f) maxDist = 10f; // fallback

        if (Physics.Raycast(start, dir, out var hit, maxDist, SatelliteLayerMask, QueryTriggerInteraction.Ignore))
        {
            // If we hit something that isn't this exact triangle, we're shadowed
            if (hit.collider != col || hit.triangleIndex != triGlobalIndex)
                return true;
        }
        return false;
    }

    // Method to estimate satellite radius 
    private float EstimateSatelliteRadiusKM()
    {
        var b = new Bounds(Source.satellite.transform.position, Vector3.zero);
        foreach (var r in Source.satellite.GetComponentsInChildren<Renderer>(true))
            b.Encapsulate(r.bounds);
        return b.extents.magnitude;
    }

    // Method to get required spectra from lightcurvegenerator
    private void EnsureSpectraFromSource()
    {
        if (_spectraReady &&
            _Esun.lam_nm != null && _QE.lam_nm != null && _WT.lam_nm != null) return;

        _Esun = LoadCsv(Source.SunSpectrumCSV);
        _QE = LoadCsv(Source.QECSV);
        _WT = LoadCsv(Source.WTCSV);

        SortByLambda(ref _Esun);
        SortByLambda(ref _QE);
        SortByLambda(ref _WT);

        _spectraReady = true;
    }

    // Method to load tabulated spectra in Curve struct
    private float ValuesParser(string s) => float.Parse(s, CultureInfo.InvariantCulture);
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

    // Method to sort spectral vurves by wavelength
    private void SortByLambda(ref Curve c)
    {
        if (c.lam_nm == null || c.y == null || c.lam_nm.Length != c.y.Length) return;
        Array.Sort(c.lam_nm, c.y);
    }

    // Method to interpolate input curve at given wavelength
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
        // Interp at
        double t = (nmf - x[i0]) / (x[i1] - x[i0]);
        return y[i0] * (1 - t) + y[i1] * t;
    }

    /// Method to compute electrons per (m^2·s) at the object surface, including Sun 1/r^2, Tatm, WT, QE, λ/hc.
    private double IntegrateElectronsPerAreaPerSecondBand(double r_SO_km, double lamMinNM, double lamMaxNM)
    {
        if (!_spectraReady) EnsureSpectraFromSource();

        double sunScale = Math.Pow(AU_KM  / r_SO_km, 2.0);
        double sum = 0.0;

        for (double a = lamMinNM; a < lamMaxNM; a += steps)
        {
            double b = Math.Min(lamMaxNM, a + steps);

            double Ea = LerpAt(_Esun, a) * sunScale;  // W m^-2 nm^-1
            double Eb = LerpAt(_Esun, b) * sunScale;

            double Ta = LerpAt(_Tatm, a);             // 0..1 (or 1 if empty)
            double Tb = LerpAt(_Tatm, b);

            double Xa = LerpAt(_WT, a);             // 0..1
            double Xb = LerpAt(_WT, b);

            double Qa = LerpAt(_QE, a);             // 0..1
            double Qb = LerpAt(_QE, b);

            // photons per joule: λ / (h c)
            double Pa = a * 1e-9 / (H * C);
            double Pb = b * 1e-9 / (H * C);

            double fa = Ea * Ta * Xa * Qa * Pa;
            double fb = Eb * Tb * Xb * Qb * Pb;

            sum += 0.5 * (fa + fb) * (b - a);        // trapezoid rule
        }

        // electrons / (m^2·s)
        return sum;
    }
    // Method to build the mesh parts cache
    private void BuildPartsCache()
    {
        _parts.Clear();

        // Loop on satellite meshes
        foreach (var mf in Source.satellite.GetComponentsInChildren<MeshFilter>(true))
        {
            // Get shared mesh
            var mesh = mf.sharedMesh;
            if (!mesh) continue;
            // Get mesh collider
            var col = mf.GetComponent<MeshCollider>();
            if (!col) col = mf.gameObject.AddComponent<MeshCollider>();
            // Set collider options
            col.cookingOptions = MeshColliderCookingOptions.None;
            col.sharedMesh = mesh;
            col.convex = false;

            // Populate class
            var p = new Part
            {
                mf = mf,
                col = col,
                mesh = mesh,
                localToWorld = mf.transform.localToWorldMatrix,
                verts = mesh.vertices,
                subMeshCount = mesh.subMeshCount,
                submeshTriOffset = new int[mesh.subMeshCount],
                materials = mf.GetComponent<MeshRenderer>()?.sharedMaterials
            };

            // Build cumulative triangle offsets per submesh for global triangle indexing
            int acc = 0;
            for (int s = 0; s < p.subMeshCount; s++)
            {
                p.submeshTriOffset[s] = acc;
                int triCount = mesh.GetTriangles(s).Length / 3;
                acc += triCount;
            }

            _parts.Add(p);
        }

        if (_parts.Count == 0)
            Debug.LogWarning("FacetFluxIntegrator: no MeshFilters found under Satellite.");
    }
    #endregion

    #region === Materials =====================================================================
    enum BrdfMode { CookTorrance = 0, BlinnPhong = 1, Lambert = 2 }

    struct BRDFParams
    {
        public Vector3 albedoRGB;       // diffuse albedo luminance (from _BaseColor)
        public Vector3 specRGB;         // specular intensity luminance (from _Specular)
        public double roughness;        // _Roughness [0..1] → alpha for GGX
        public double F0;               // _Fresnel scalar [0..1]
        public double shininess;        // _Shininess for Blinn-Phong
        public BrdfMode mode;           // _BRDF enum
        public bool receiveShadows;     // _ReceiveShadows != 0
    }
    // Method to read the BRDF paarmeters of a material
    BRDFParams GetBRDFParams(Material mat)
    {
        // Defaults
        double rough = 0.5, F0 = 0.9, shininess = 32, brdf = 0, recv = 1;
        Vector3 albedoRGB = new Vector3(0f, 0f, 0f);
        Vector3 specRGB = new Vector3(0f, 0f, 0f);

        if (mat != null)
        {
            if (mat.HasProperty("_BaseColor"))
            {
                var c = mat.GetColor("_BaseColor");
                albedoRGB = new Vector3(c.r, c.g, c.b);
            }
            else if (mat.HasProperty("_Color"))
            {
                var c = mat.GetColor("_Color");
                albedoRGB = new Vector3(c.r, c.g, c.b);
            }

            if (mat.HasProperty("_Specular"))
            {
                var s = mat.GetColor("_Specular");
                specRGB = new Vector3(s.r, s.g, s.b);
            }

            if (mat.HasProperty("_Roughness"))
                rough = Mathf.Clamp(mat.GetFloat("_Roughness"), 0.0f, 1.0f);

            if (mat.HasProperty("_Fresnel"))
                F0 = Mathf.Clamp01(mat.GetFloat("_Fresnel"));

            if (mat.HasProperty("_Shininess"))
                shininess = Math.Max(1.0f, mat.GetFloat("_Shininess"));

            if (mat.HasProperty("_BRDF"))
                brdf = mat.GetFloat("_BRDF");

            if (mat.HasProperty("_ReceiveShadows"))
                recv = mat.GetFloat("_ReceiveShadows");
        }

        return new BRDFParams
        {
            albedoRGB = albedoRGB,
            specRGB = specRGB,
            roughness = rough,
            F0 = F0,
            shininess = shininess,
            mode = (BrdfMode)Mathf.RoundToInt((float)brdf),
            receiveShadows = recv != 0
        };
    }

    // Method to evaluate a facet BRDF (sr^-1) using custom models
    private (double r, double g, double b) EvaluateBRDF(in BRDFParams p, Vector3 N, Vector3 V, Vector3 L)
    {
        // Cosines
        Vector3 H = V + L;
        float hlen = H.magnitude;
        if (hlen < 1e-8f) return (0.0, 0.0, 0.0);
        H /= hlen;

        double NdotL = Math.Max(0.0f, Vector3.Dot(N, L));
        double NdotV = Math.Max(0.0f, Vector3.Dot(N, V));
        double NdotH = Math.Max(0.0f, Vector3.Dot(N, H));
        double VdotH = Math.Max(0.0f, Vector3.Dot(V, H));
        double LdotH = Math.Max(0.0f, Vector3.Dot(L, H));

        if (NdotL <= 0.0 || NdotV <= 0.0) return (0.0, 0.0, 0.0);
 
        double specMax = Math.Min(1.0, Math.Max(p.specRGB.x, Math.Max(p.specRGB.y, p.specRGB.z)));
        double diffuseFactor = Math.Max(0.0, 1.0 - specMax);

        // Lambert diffuse (per channel)
        double diffR = diffuseFactor * p.albedoRGB.x / Math.PI;
        double diffG = diffuseFactor * p.albedoRGB.y / Math.PI;
        double diffB = diffuseFactor * p.albedoRGB.z / Math.PI;

        double specTerm = 0.0;

        switch (p.mode)
        {
            case BrdfMode.CookTorrance:
                {
                    double alpha = Clamp(Math.Max(0.04, p.roughness), 0.04, 1.0);

                    // Walters GGX Distribution
                    double D = DistributionGGX(NdotH, alpha);

                    // Smith GGX geometry
                    double G1v = GGX_PartialGeometry(VdotH, NdotV, alpha);
                    double G1l = GGX_PartialGeometry(LdotH, NdotL, alpha);
                    double G = G1v * G1l;

                    // Schlick Fresnel with scalar F0
                    double F = Schlick(VdotH, p.F0);

                    // Specular BRDF (sr^-1)
                    double denom = Math.Max(1e-6, 4.0 * NdotL * NdotV);
                    specTerm = F * D * G / denom;
                    break;
                }

            case BrdfMode.BlinnPhong:
                {
                    double n = Math.Max(1.0, p.shininess);
                    double norm = (n + 8.0) / (8.0 * Math.PI);
                    specTerm = norm * Math.Pow(NdotH, n);
                    break;
                }

            case BrdfMode.Lambert:
            default:
                {
                    specTerm = 0.0;
                    break;
                }
        }
        double specR = p.specRGB.x * specTerm;
        double specG = p.specRGB.y * specTerm;
        double specB = p.specRGB.z * specTerm;

        return (diffR + specR, diffG + specG, diffB + specB);
    }

    // BRDF helpers
    private double Clamp(double v, double a, double b) => v < a ? a : (v > b ? b : v);

    private double chi(double v) => v > 0.0 ? 1.0 : 0.0;

    private double DistributionGGX(double NdotH, double alpha)
    {
        double a2 = alpha * alpha;
        double NoH = Math.Max(0.0, NdotH);
        double NoH2 = NoH * NoH;
        double den = NoH2 * a2 + (1.0 - NoH2);
        return chi(NdotH) * a2 / (Math.PI * den * den + 1e-12);
    }

    private double GGX_PartialGeometry(double XdotH, double XdotN, double alpha)
    {
        double XoH = Math.Max(0.0, XdotH);
        double XoN = Math.Max(1e-6, XdotN);
        if (XoH / XoN <= 0.0) return 0.0;

        double XoH2 = XoH * XoH;
        double tan2 = (1.0 - XoH2) / Math.Max(1e-12, XoH2);
        return 2.0 / (1.0 + Math.Sqrt(1.0 + (alpha * alpha) * tan2));
    }

    private double Schlick(double cosTheta, double F0)
    {
        double oneMinus = 1.0 - Math.Max(0.0, cosTheta);
        return F0 + (1.0 - F0) * oneMinus * oneMinus * oneMinus * oneMinus * oneMinus;
    }
    private double Clamp01(double v) => v < 0 ? 0 : (v > 1 ? 1 : v);
    #endregion
}

