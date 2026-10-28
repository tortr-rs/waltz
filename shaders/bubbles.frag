// glossy bubbles rising through a sky-to-sea gradient, frutiger aero style

float hash(float n) { return fract(sin(n) * 43758.5453); }

void mainImage(out vec4 fragColor, in vec2 fragCoord)
{
    vec2 uv = fragCoord / iResolution.xy;
    float aspect = iResolution.x / iResolution.y;
    vec3 col = mix(vec3(0.02, 0.38, 0.62), vec3(0.55, 0.88, 1.0), uv.y);
    // soft light rays from the top left
    float ray = sin((uv.x - uv.y * 0.6) * 18.0 + iTime * 0.2) * 0.5 + 0.5;
    col += vec3(0.08, 0.12, 0.14) * pow(ray, 6.0) * uv.y;

    vec2 p = vec2(uv.x * aspect, uv.y);
    for (int i = 0; i < 28; i++) {
        float fi = float(i);
        float r = 0.02 + 0.06 * hash(fi * 7.1);
        float speed = 0.03 + 0.05 * hash(fi * 3.7);
        float x = hash(fi * 1.3) * aspect + 0.04 * sin(iTime * 0.5 + fi);
        float y = fract(hash(fi * 5.9) + iTime * speed) * 1.3 - 0.15;
        vec2 d = p - vec2(x, y);
        float dist = length(d);
        if (dist < r) {
            float e = dist / r;
            // clear middle, bright rim, a shine at the top left
            float rim = smoothstep(0.75, 1.0, e);
            float shine = smoothstep(0.35, 0.0, length(d / r - vec2(-0.35, 0.4)));
            col = mix(col, vec3(0.75, 0.95, 1.0), rim * 0.55 + shine * 0.8);
            col += vec3(0.05, 0.1, 0.1) * (1.0 - e);
        }
    }
    fragColor = vec4(col, 1.0);
}
