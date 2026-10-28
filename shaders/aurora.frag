// slow green and violet curtains over a night sky

float wave(vec2 p, float t, float k)
{
    return sin(p.x * k + t) * 0.5 + sin(p.x * k * 2.3 - t * 1.3) * 0.25;
}

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord / iResolution.xy;
    float t = iTime * 0.15;
    vec3 col = mix(vec3(0.0, 0.01, 0.04), vec3(0.02, 0.05, 0.12), uv.y);
    for (int i = 0; i < 3; i++) {
        float fi = float(i);
        float h = 0.55 + 0.1 * fi + 0.08 * wave(uv, t + fi, 3.0 + fi);
        float band = exp(-pow((uv.y - h) * 9.0, 2.0)) * smoothstep(0.0, 0.6, uv.y);
        vec3 tint = mix(vec3(0.1, 0.9, 0.5), vec3(0.6, 0.3, 0.9), fi / 2.0);
        col += tint * band * (0.5 + 0.5 * sin(uv.x * 40.0 + t * 8.0 + fi)) * 0.6;
    }
    // a few stars
    vec2 s = floor(fragCoord / 3.0);
    float star = step(0.9985, fract(sin(dot(s, vec2(12.9898, 78.233))) * 43758.5453));
    col += star * (0.6 + 0.4 * sin(iTime * 2.0 + s.x)) * uv.y;
    fragColor = vec4(col, 1.0);
}
