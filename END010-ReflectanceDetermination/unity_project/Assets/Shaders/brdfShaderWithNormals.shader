Shader "Custom/brdfShaderWithNormals"
{
    Properties
    {
        _BaseColor ("Albedo", Color) = (1,1,1,1)
        _Specular  ("Specular (ks)",  Color) = (1,1,1,1)
        _Roughness ("Roughness (alpha)", Range(0,1)) = 0.5
        _Fresnel ("Fresnel (F0)", Range(0,1)) = 0.9
        _Shininess ("Shininess (n)", Range(1,256)) = 32

        [Normal] _NormalMap ("Normal Map", 2D) = "bump" {}
        _NormalScale ("Normal Strength", Range(0,2)) = 1.0

        [KeywordEnum(CookTorrance, BlinnPhong, Lambert)] _BRDF ("Shading Model", Float) = 0
        [ToggleUI] _ReceiveShadows("Receive Shadows", Float) = 1.0
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline"  = "UniversalPipeline"
            "Queue"           = "Geometry"
            "RenderType"      = "Opaque"
            "IgnoreProjector" = "True"
        }
        LOD 300

        Pass
        {
            Name "ForwardPass"
            Tags { "LightMode"="UniversalForward" }
            ZWrite On

            HLSLPROGRAM

            #pragma vertex   vert
            #pragma fragment frag
            #pragma shader_feature_local _BRDF_COOKTORRANCE _BRDF_BLINNPHONG _BRDF_LAMBERT
            #pragma enable_d3d11_debug_symbols
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _SHADOWS_SOFT

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseColor;
                float4 _Specular;
                float  _Roughness;
                float  _Fresnel;
                float  _Shininess;
                float  _ReceiveShadows;
                float  _NormalScale;
                float4 _NormalMap_ST;
            CBUFFER_END

            TEXTURE2D(_NormalMap);
            SAMPLER(sampler_NormalMap);

            struct Attributes
            {
                float3 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float4 tangentOS  : TANGENT;
                float2 uv         : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS   : SV_POSITION;
                float3 positionWS   : TEXCOORD0;
                float3 normalWS     : TEXCOORD1;
                float2 uv           : TEXCOORD2;
                float4 shadowCoords : TEXCOORD3;
                float3 tangentWS    : TEXCOORD4;
                float3 bitangentWS  : TEXCOORD5;
            };

            Varyings vert (Attributes IN)
            {
                Varyings OUT;

                VertexPositionInputs posInput = GetVertexPositionInputs(IN.positionOS.xyz);
                VertexNormalInputs   nrmInput = GetVertexNormalInputs(IN.normalOS, IN.tangentOS);

                OUT.positionWS   = posInput.positionWS;
                OUT.positionCS   = posInput.positionCS;
                OUT.shadowCoords = GetShadowCoord(posInput);

                OUT.normalWS     = nrmInput.normalWS;
                OUT.tangentWS    = nrmInput.tangentWS;
                OUT.bitangentWS  = nrmInput.bitangentWS;

                OUT.uv           = TRANSFORM_TEX(IN.uv, _NormalMap);

                return OUT;
            }

            float chiGGX(float v)
            {
                return v > 0 ? 1 : 0;
            }

            float GGX_PartialGeometryTerm(float XdotH, float XdotN, float alpha)
            {
                float XoH2 = saturate(XdotH);
                float chi  = chiGGX(XoH2 / max(saturate(XdotN), 1e-6));
                XoH2 = XoH2 * XoH2;
                float tan2 = (1 - XoH2) / max(XoH2, 1e-6);
                return (chi * 2) / (1 + sqrt(1 + alpha * alpha * tan2));
            }

            float Fresnel(float c, float F0)
            {
                float n = (1 + sqrt(F0)) / max(1 - sqrt(F0), 1e-6);
                float g = sqrt(n * n + c * c - 1);
                float F = 0.5 * pow(g - c, 2) / max(pow(g + c, 2), 1e-6) *
                          (1 + pow(c * (g + c) - 1, 2) / max(pow(c * (g - c) - 1, 2), 1e-6));

                // Schlick approximation
                F = F0 + (1.0 - F0) * pow(1.0 - c, 5.0);
                return F;
            }

            float DistributionGGX(float NdotH, float alpha)
            {
                float alpha2 = alpha * alpha;
                float NoH2   = NdotH * NdotH;
                float den    = NoH2 * alpha2 + (1 - NoH2);
                return (chiGGX(NdotH) * alpha2) / max(PI * den * den, 1e-6);
            }

            float3 GetNormalWS(Varyings IN)
            {
                float3 normalTS = UnpackNormalScale(
                    SAMPLE_TEXTURE2D(_NormalMap, sampler_NormalMap, IN.uv),
                    _NormalScale
                );

                float3x3 TBN = float3x3(
                    normalize(IN.tangentWS),
                    normalize(IN.bitangentWS),
                    normalize(IN.normalWS)
                );

                return normalize(mul(normalTS, TBN));
            }

            float4 frag (Varyings IN) : SV_Target
            {
                float3 spec;
                float3 diff;

                Light main = GetMainLight();

                float3 N = GetNormalWS(IN);
                float3 V = normalize(_WorldSpaceCameraPos - IN.positionWS);
                float3 L = normalize(main.direction);
                float3 H = normalize(V + L);

                float NdotL = saturate(dot(N, L));
                float NdotV = saturate(dot(N, V));
                float NdotH = saturate(dot(N, H));
                float VdotH = saturate(dot(V, H));
                float LdotH = saturate(dot(L, H));

                float3 albedo   = _BaseColor.rgb;
                float3 specular = saturate(_Specular.rgb);
                float  diffuse  = 1.0 - Max3(_Specular.r, _Specular.g, _Specular.b);
                float  alpha    = clamp(_Roughness, 0.04, 1.0);

                #if defined(_BRDF_COOKTORRANCE)
                {
                    float  F  = Fresnel(VdotH, _Fresnel);
                    float  D  = DistributionGGX(NdotH, alpha);
                    float  G1 = GGX_PartialGeometryTerm(VdotH, NdotV, alpha);
                    float  G2 = GGX_PartialGeometryTerm(LdotH, NdotL, alpha);
                    float  G  = G1 * G2;

                    float3 specularTerm = F * D * G / max(4.0 * NdotL * NdotV, 1e-4);
                    spec = specular * specularTerm;
                    diff = diffuse * albedo / PI;
                }
                #elif defined(_BRDF_BLINNPHONG)
                {
                    float3 specularTerm = pow(saturate(NdotH), _Shininess);
                    spec = specular * specularTerm;
                    diff = diffuse * albedo / PI;
                }
                #else
                {
                    spec = 0;
                    diff = albedo * (1.0 / PI);
                }
                #endif

                float3 Li = main.color;

                float shadow = 1.0;
                if (_ReceiveShadows > 0.5)
                {
                    shadow = MainLightRealtimeShadow(IN.shadowCoords);
                }

                float3 Lo = Li * NdotL * shadow * (diff + spec);
                return float4(Lo, 1);
            }

            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode"="ShadowCaster" }

            ColorMask 0

            HLSLPROGRAM

            #pragma vertex vert
            #pragma fragment frag
            #pragma enable_d3d11_debug_symbols

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            struct Attributes
            {
                float3 positionOS : POSITION;
                float3 normalOS   : NORMAL;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
            };

            float4 GetShadowPositionHClip(Attributes IN)
            {
                Light main = GetMainLight();
                float3 positionWS = TransformObjectToWorld(IN.positionOS.xyz);
                float3 normalWS   = TransformObjectToWorldNormal(IN.normalOS);
                float4 positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, main.direction));
                positionCS = ApplyShadowClamping(positionCS);
                return positionCS;
            }

            Varyings vert (Attributes IN)
            {
                Varyings OUT;
                OUT.positionCS = GetShadowPositionHClip(IN);
                return OUT;
            }

            float4 frag (Varyings IN) : SV_Target
            {
                return 0;
            }

            ENDHLSL
        }
    }

    FallBack Off
}