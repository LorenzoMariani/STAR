using System;
using System.Globalization;
using UnityEngine;

// STAR END-010: the scene carries the five NASA-style CDS CubeSat models (1U, 2U, 3U, 6U, 12U) as children of the satellite object;
// -cubesatClass <1|2|3|6|12> on the command line keeps the matching one active (default: DefaultClass). Runs before CsvLoader and
// LightCurveGenerator so that only the chosen model is rendered.
[DefaultExecutionOrder(-300)]
public class StarCubeSatSelector : MonoBehaviour
{
    [Tooltip("Class used when -cubesatClass is not given")]
    public int DefaultClass = 6;

    private void Awake()
    {
        int units = DefaultClass;
        string[] cli = Environment.GetCommandLineArgs();
        for (int i = 0; i + 1 < cli.Length; i++)
        {
            if (cli[i] == "-cubesatClass" && int.TryParse(cli[i + 1], NumberStyles.Integer, CultureInfo.InvariantCulture, out int v))
                units = v;
        }
        string wanted = $"CubeSat_{units}U";
        bool found = false;
        var others = new System.Collections.Generic.List<GameObject>();
        foreach (Transform child in transform)
        {
            if (!child.name.StartsWith("CubeSat_")) continue;
            if (child.name == wanted) { child.gameObject.SetActive(true); found = true; }
            else others.Add(child.gameObject);
        }
        // the other models are removed, not only hidden: the clip planes (LightCurveGenerator) and the facet sum (FacetFluxIntegrator)
        // read the renderers and meshes of inactive children too
        if (found)
            foreach (var go in others) DestroyImmediate(go);
        if (!found)
            Debug.LogError($"StarCubeSatSelector: no model {wanted} in the scene (allowed: 1, 2, 3, 6, 12)");
        else
            Debug.Log($"StarCubeSatSelector: rendering {wanted}");
    }
}
