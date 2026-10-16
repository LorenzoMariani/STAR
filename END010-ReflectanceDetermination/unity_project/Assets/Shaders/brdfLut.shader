Shader "Custom/brdfLut"
{
    Properties
    {
        _LutIntensity ("LUT Intensity", Range(0,10)) = 1.0
        [ToggleUI] _DebugOutOfRange("Debug out-of-range (magenta)", Float) = 1.0
    }

    SubShader
    {
        Tags { "RenderPipeline"="UniversalPipeline" "Queue"="Geometry" "RenderType"="Opaque" }

        Pass
        {
            Name "ForwardPass"
            Tags { "LightMode"="UniversalForward" }
            ZWrite On

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float _LutIntensity;
                float _DebugOutOfRange;
            CBUFFER_END

            StructuredBuffer<float4> _BrdfLutRgb;

            int _nAzL, _nThL, _nAzC, _nThC;
            float _azMinL, _thMinL, _azMinC, _thMinC;
            float _azStepL, _thStepL, _azStepC, _thStepC;

            struct Attributes { float3 positionOS : POSITION; float3 normalOS : NORMAL; };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
            };

            Varyings vert(Attributes IN)
            {
                Varyings OUT;
                OUT.positionWS = TransformObjectToWorld(IN.positionOS.xyz);
                OUT.positionCS = TransformWorldToHClip(OUT.positionWS);
                OUT.normalWS   = TransformObjectToWorldNormal(IN.normalOS);
                return OUT;
            }

            uint idx4(int iAzL, int iThL, int iAzC, int iThC)
            {
                return (uint)(iAzL + _nAzL * (iThL + _nThL * (iAzC + _nAzC * iThC)));
            }

            float3 fetchRGB(int iAzL, int iThL, int iAzC, int iThC)
            {
                iAzL = clamp(iAzL, 0, _nAzL - 1);
                iThL = clamp(iThL, 0, _nThL - 1);
                iAzC = clamp(iAzC, 0, _nAzC - 1);
                iThC = clamp(iThC, 0, _nThC - 1);
                return _BrdfLutRgb[idx4(iAzL,iThL,iAzC,iThC)].xyz;
            }

            void angleToCell(float azDeg, float thDeg,
                             float azMin, float thMin, float azStep, float thStep,
                             int nAz, int nTh,
                             out int ia0, out int ia1, out float ta,
                             out int it0, out int it1, out float tt)
            {
                azDeg = azDeg - 360.0 * floor(azDeg / 360.0);

                float ua = (azDeg - azMin) / azStep;
                ia0 = (int)floor(ua); ta = frac(ua);
                ia0 = clamp(ia0, 0, nAz - 2); ia1 = ia0 + 1;

                float ut = (thDeg - thMin) / thStep;
                it0 = (int)floor(ut); tt = frac(ut);
                it0 = clamp(it0, 0, nTh - 2); it1 = it0 + 1;
            }

            float3 sampleLUT_RGB(float azL, float thL, float azC, float thC)
            {
                int aL0,aL1,tL0,tL1,aC0,aC1,tC0,tC1;
                float faL,ftL,faC,ftC;

                angleToCell(azL, thL, _azMinL, _thMinL, _azStepL, _thStepL, _nAzL, _nThL,
                            aL0,aL1,faL, tL0,tL1,ftL);

                angleToCell(azC, thC, _azMinC, _thMinC, _azStepC, _thStepC, _nAzC, _nThC,
                            aC0,aC1,faC, tC0,tC1,ftC);

                float3 c0000 = fetchRGB(aL0,tL0,aC0,tC0);
                float3 c0001 = fetchRGB(aL0,tL0,aC0,tC1);
                float3 c0010 = fetchRGB(aL0,tL0,aC1,tC0);
                float3 c0011 = fetchRGB(aL0,tL0,aC1,tC1);

                float3 c0100 = fetchRGB(aL0,tL1,aC0,tC0);
                float3 c0101 = fetchRGB(aL0,tL1,aC0,tC1);
                float3 c0110 = fetchRGB(aL0,tL1,aC1,tC0);
                float3 c0111 = fetchRGB(aL0,tL1,aC1,tC1);

                float3 c1000 = fetchRGB(aL1,tL0,aC0,tC0);
                float3 c1001 = fetchRGB(aL1,tL0,aC0,tC1);
                float3 c1010 = fetchRGB(aL1,tL0,aC1,tC0);
                float3 c1011 = fetchRGB(aL1,tL0,aC1,tC1);

                float3 c1100 = fetchRGB(aL1,tL1,aC0,tC0);
                float3 c1101 = fetchRGB(aL1,tL1,aC0,tC1);
                float3 c1110 = fetchRGB(aL1,tL1,aC1,tC0);
                float3 c1111 = fetchRGB(aL1,tL1,aC1,tC1);

                float3 w000 = lerp(lerp(c0000, c0001, ftC), lerp(c0010, c0011, ftC), faC);
                float3 w010 = lerp(lerp(c0100, c0101, ftC), lerp(c0110, c0111, ftC), faC);
                float3 w100 = lerp(lerp(c1000, c1001, ftC), lerp(c1010, c1011, ftC), faC);
                float3 w110 = lerp(lerp(c1100, c1101, ftC), lerp(c1110, c1111, ftC), faC);

                float3 w00 = lerp(w000, w010, ftL);
                float3 w10 = lerp(w100, w110, ftL);
                return lerp(w00, w10, faL);
            }

            void buildStableFrame(float3 N, out float3 T, out float3 B)
            {
                float3 ref = (abs(N.y) < 0.999) ? float3(0,1,0) : float3(1,0,0);
                T = normalize(cross(ref, N));
                B = cross(N, T);
            }

            void dirToAzThDeg(float3 D, float3 N, float3 T, float3 B, out float azDeg, out float thDeg)
            {
                float z = clamp(dot(N, D), -1.0, 1.0);
                thDeg = degrees(acos(z));
                float x = dot(D, T);
                float y = dot(D, B);
                azDeg = degrees(atan2(y, x));
                if (azDeg < 0) azDeg += 360.0;
            }

            float4 frag(Varyings IN) : SV_Target
            {
                float3 N = normalize(IN.normalWS);
                float3 V = normalize(_WorldSpaceCameraPos - IN.positionWS);

                Light main = GetMainLight();
                float3 L = normalize(main.direction);

                float3 T, B;
                buildStableFrame(N, T, B);

                float azL, thL, azV, thV;
                dirToAzThDeg(L, N, T, B, azL, thL);
                dirToAzThDeg(V, N, T, B, azV, thV);

                if (_DebugOutOfRange > 0.5)
                {
                    float thMaxL = _thMinL + _thStepL * (_nThL - 1);
                    float thMaxC = _thMinC + _thStepC * (_nThC - 1);
                    if (thL < _thMinL || thL > thMaxL || thV < _thMinC || thV > thMaxC)
                        return float4(1,0,1,1);
                }

                float3 fr = sampleLUT_RGB(azL, thL, azV, thV) * _LutIntensity;
                return float4(fr, 1);
            }

            ENDHLSL
        }
    }
    FallBack Off
}