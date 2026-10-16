Shader "Custom/brdfShader"
{   
    // Material properties (to be defined in HLSL with CBUFFER_START)
    Properties
    {
        _BaseColor ("Albedo", Color) = (1,1,1,1)
        _Specular  ("Specular (ks)",  Color) = (1,1,1,1)
        _Roughness ("Roughness (alpha)", Range(0,1)) = 0.5
        _Fresnel ("Fresnel (F0)", Range(0,1)) = 0.9
        _Shininess ("Shininess (n)", Range(1,256)) = 32
        [KeywordEnum(CookTorrance, BlinnPhong, Lambert)] _BRDF ("Shading Model", Float) = 0
        [ToggleUI] _ReceiveShadows("Receive Shadows", Float) = 1.0
    }

    SubShader
    {
        Tags { "RenderPipeline"  = "UniversalPipeline"
               "Queue"           = "Geometry" 
               "RenderType"      = "Opaque"
               "IgnoreProjector" = "True" }
        LOD 300

        Pass
        {
            Name "ForwardPass"
            Tags { "LightMode"="UniversalForward" }
            ZWrite On

            // Start HLSL code
            HLSLPROGRAM

            #pragma vertex   vert                                                                              // define the vertex shader function
            #pragma fragment frag                                                                              // define the fragment shader function
            #pragma shader_feature_local _BRDF_COOKTORRANCE _BRDF_BLINNPHONG _BRDF_LAMBERT
            #pragma enable_d3d11_debug_symbols
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _SHADOWS_SOFT

            // Include frequently used libraries and macros
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            // Buffer for material properties (to be passed to GPU)
            CBUFFER_START(UnityPerMaterial)
                float4 _BaseColor;
                float4  _Specular;
                float  _Roughness;
                float  _Fresnel;
                float  _Shininess;
                float  _ReceiveShadows;
            CBUFFER_END

            struct Attributes
            { 
                float3 positionOS :POSITION;   // Vertex position in object space
                float3 normalOS   :NORMAL;     // Vertex normal in object space          
                float2 uv         :TEXCOORD0;  // Vertex UV coordinates
            };

            struct Varyings
            {
                float4 positionCS   :SV_POSITION; // Vertex position in clip space
                float3 positionWS   :TEXCOORD0;   // Vertex position in world space to be passed to GPU (interpolated)
                float3 normalWS     :TEXCOORD1;   // Vertex normals in world space to be passed to GPU (interpolated)
                float2 uv           :TEXCOORD2;
                float4 shadowCoords :TEXCOORD3;
            };

            // VERTEX SHADER FUNCTION
            Varyings vert (Attributes IN)
            {
                Varyings OUT;
                OUT.positionWS  = TransformObjectToWorld(IN.positionOS.xyz);
                OUT.positionCS  = TransformWorldToHClip(OUT.positionWS.xyz);
                OUT.normalWS    = TransformObjectToWorldNormal(IN.normalOS);

                // Convert the vertex position to a position on the shadow map
                VertexPositionInputs posInput = GetVertexPositionInputs(IN.positionOS.xyz);
                
                OUT.shadowCoords = GetShadowCoord(posInput);
                OUT.uv           = IN.uv;
                return OUT;
            }

            //-----------------------------------------------------------------------
            // HELPERS FOR FRAGMENT SHADER
            // ----------------------------------------------------------------------
            
            float chiGGX(float v)
            {
                return v > 0 ? 1 : 0;
            }

            // Distribution function for GGX microfacet model (Walters 2007)
            float GGX_PartialGeometryTerm(float XdotH, float XdotN, float alpha)
            {
                float XoH2 = saturate(XdotH);
                float chi  = chiGGX( XoH2 / saturate(XdotN) );
                XoH2 = XoH2 * XoH2;
                float tan2 = ( 1 - XoH2 ) / XoH2;
                return (chi * 2) / ( 1 + sqrt( 1 + alpha * alpha * tan2 ) );
            }

            // Fresnel term from Cook-Torrance 82
            float Fresnel(float c, float F0)
            {
                float n = (1+sqrt(F0))/(1-sqrt(F0));
                float g = sqrt(pow(n,2) + pow(c, 2) - 1);
                float F = 0.5*pow(g-c,2)/pow(g+c,2)*(1+ (pow(c*(g+c)-1,2))/(pow(c*(g-c)-1,2)));
                // Alternative Schlick approximation
                F = F0 + (1.0 - F0) * pow(1.0 - c, 5.0);
                return F; 
            }

            // Compute microfacet distribution (GGX Walters 2007)
            float DistributionGGX(float NdotH, float alpha)
            {
                float alpha2 = alpha * alpha;
                float NoH2   = NdotH * NdotH;
                float den    = NoH2 * alpha2 + (1 - NoH2);
                return (chiGGX(NdotH) * alpha2) / ( PI * den * den );
            }

            // FRAGMENT SHADER FUNCTION - NB: directions are outside the surface
            float4 frag (Varyings IN) : SV_Target
            {   
                float3 spec;
                float3 diff;

                // Get the main light direction and color
                Light  main = GetMainLight();
                float3 N = normalize(IN.normalWS);
                // View direction
                float3 V    = normalize(_WorldSpaceCameraPos - IN.positionWS);
                // Light direction
                float3 L    = normalize(main.direction);
                // Half vector
                float3 H    = normalize(V + L);
                // Dot products
                float NdotL = saturate(dot(N,L));
                float NdotV = saturate(dot(N,V));
                float NdotH = saturate(dot(N,H));
                float VdotH = saturate(dot(V,H));
                float LdotH = saturate(dot(L,H));
                // Material
                float3 albedo   = _BaseColor.rgb;
                float3 specular = saturate(_Specular.rgb);
                float  diffuse  = 1.0 - Max3(_Specular.r, _Specular.g, _Specular.b);
                float  alpha    = clamp(_Roughness, 0.04, 1.0);
                // BRDF
                #if defined(_BRDF_COOKTORRANCE)
                {
                    float F  = Fresnel(VdotH, _Fresnel);
                    float D  = DistributionGGX(NdotH, alpha);
                    float G1 = GGX_PartialGeometryTerm(VdotH, NdotV, alpha);
                    float G2 = GGX_PartialGeometryTerm(LdotH, NdotL, alpha);
                    float G  = G1 * G2;
                    float3 specularTerm = F * D * G / (4.0 * NdotL * NdotV + 1e-4);
                    spec =  specular * specularTerm;
                    diff =  diffuse  * albedo / PI;

                }
                #elif defined(_BRDF_BLINNPHONG)
                {
                    float3 specularTerm = pow(saturate(NdotH), _Shininess);
                    spec = specular * specularTerm;
                    diff = diffuse  * albedo / PI;
                }
                #else
                {
                    spec = 0;
                    diff = albedo * (1.0/PI);
                }
                #endif

                // Input light
                float3 Li = main.color;

                // Compute shadow
                float shadow = 1.0;
                if (_ReceiveShadows)
                {
                    shadow = MainLightRealtimeShadow(IN.shadowCoords);
                }
                // Final color
                float3 Lo = Li * NdotL * shadow * (diff + spec);
                return float4(Lo,1);
            }
            ENDHLSL
            // End HLSL code
        }
        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode"="ShadowCaster" }

            ColorMask 0 // Disable color output for shadow caster pass

            // Start HLSL code
            HLSLPROGRAM

            #pragma vertex vert
            #pragma fragment frag
            #pragma enable_d3d11_debug_symbols
        
            // Include frequently used libraries and macros
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            struct Attributes
            {
                float3 positionOS : POSITION;   // Vertex position in object space
                float3 normalOS   : NORMAL;     // Vertex normal in object space          
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION; // Vertex position in clip space
            };

            float4 GetShadowPositionHClip(Attributes IN)
            {   
                Light main = GetMainLight();
                float3 positionsWS = TransformObjectToWorld(IN.positionOS.xyz);
                float3 normalWS    = TransformObjectToWorldNormal(IN.normalOS);
                float4 positionCS  = TransformWorldToHClip(ApplyShadowBias(positionsWS, normalWS, main.direction));
                positionCS  = ApplyShadowClamping(positionCS);
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
                // Dummy
                return 0;
            }

            ENDHLSL
            // End HLSL code
        }
    }
    FallBack Off
}
