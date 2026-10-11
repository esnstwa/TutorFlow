"""Browser regression check. Run against a local TutorFlow server.

Requires playwright and installed Edge. No account is submitted to a backend.
python scripts/check_augustin_route.py [http://127.0.0.1:8000]
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000') + '/register'
QA = Path(__file__).resolve().parents[1] / 'tmp/augustin-qa'
QA.mkdir(parents=True, exist_ok=True)

SAMPLE = """() => {
  const layer = document.querySelector('.register-route-character');
  const sprite = layer.querySelector('.register-route-character__sprite');
  const spriteStyle = getComputedStyle(sprite);
  const box = layer.getBoundingClientRect();
  const layerStyle = getComputedStyle(layer);
  const characterWidth = parseFloat(layerStyle.width);
  const characterHeight = parseFloat(layerStyle.height);
  const active = document.querySelector('[data-register-progress].is-active');
  return {step: +active.dataset.registerProgress, busy: document.querySelector('.register-main').inert,
    dpr: window.devicePixelRatio || 1,
    count: sprite.isConnected ? 1 : 0,
    opacity: +spriteStyle.opacity, containerOpacity: +layerStyle.opacity,
    src: sprite.currentSrc, mood: layer.dataset.routeCharacterMood,
    x: box.x + box.width / 2, y: box.y + box.height / 2,
    visualBottom: box.y + box.height / 2 + characterHeight * (200 / 210 - .5),
    width: characterWidth, height: characterHeight,
    transform: layerStyle.transform, inlineTransform: layer.style.transform,
    scaleY: new DOMMatrixReadOnly(layerStyle.transform).d,
    pathProgress: parseFloat(layerStyle.offsetDistance),
    markers: [...document.querySelectorAll('[data-register-progress] > span')].map(n => {
      const b = n.getBoundingClientRect(); return {x:b.x+b.width/2, y:b.y+b.height/2, top:b.top};
    }), route: document.querySelector('.register-progress').getBoundingClientRect().toJSON(),
    workspace: document.querySelector('.register-workspace').getBoundingClientRect().toJSON()};
}"""


def at_step(page, step):
    page.wait_for_function(f"!document.querySelector('.register-main').inert && document.querySelector('[data-register-progress=\"{step}\"]').classList.contains('is-active')")
    state = page.evaluate(SAMPLE)
    marker = state['markers'][step-1]
    assert abs(state['x']-marker['x']) <= .51 / state['dpr'], state
    assert 8.4 <= marker['top'] - state['visualBottom'] <= 9.6, state
    assert state['count'] == 1
    assert state['mood'] == ('happy' if step == 5 else 'idle')
    return state


def jump(page, selector, target, *, rapid=False, resize=False, reduced=False):
    before = page.evaluate(SAMPLE)
    page.evaluate("window.routeSample = " + SAMPLE)
    page.evaluate("""({selector, rapid}) => {
      window.routeSamples = [];
      window.routeDone = new Promise(resolve => {
        const started = performance.now();
        let sawBusy = false;
        const tick = () => {
          routeSamples.push({...routeSample(), time:performance.now()-started});
          const busy = document.querySelector('.register-main').inert;
          sawBusy ||= busy;
          if (!sawBusy || busy) requestAnimationFrame(tick);
          else resolve(routeSamples);
        };
        const element = document.querySelector(selector);
        const act = () => element.tagName === 'FORM' ? element.requestSubmit() : element.click();
        act();
        if (rapid) for (let i=0; i<30; i++) act();
        requestAnimationFrame(tick);
      });
    }""", {'selector': selector, 'rapid': rapid})
    if resize:
        page.wait_for_timeout(180)
        page.set_viewport_size({'width': 390, 'height': 844})
    samples = page.evaluate('window.routeDone')
    after = at_step(page, target)
    assert all(s['count'] == 1 for s in samples), 'Sprite DOM element was replaced or removed'
    assert all(s['opacity'] == 1 for s in samples), 'Sprite opacity changed during jump'
    assert all(s['containerOpacity'] == 1 for s in samples), 'Container opacity changed during jump'
    if target == 5:
        assert all(s['src'] == before['src'] for s in samples if s['time'] < 800), \
            'Happy sprite appeared before landing'
        changed = [s for s in samples if s['src'] != before['src']]
        assert all(abs(s['x']-after['x']) <= .51 / s['dpr'] and abs(s['y']-after['y']) <= .51 / s['dpr'] for s in changed), \
            'Happy sprite appeared before translate completed'
        assert after['src'] != before['src'] and after['mood'] == 'happy'
    elif before['step'] == 5:
        assert all(s['src'] == after['src'] for s in samples), 'Happy sprite remained during return jump'
        assert after['src'] != before['src'] and after['mood'] == 'idle'
    else:
        assert all(s['src'] == before['src'] for s in samples), 'Sprite source changed during jump'
    assert all(s['step'] == before['step'] for s in samples if s['busy']), 'Early step change'
    if not resize:
        assert all(abs(s['width']-before['width']) < .02 and abs(s['height']-before['height']) < .02 for s in samples)
        assert all(s['route'] == before['route'] and s['workspace'] == before['workspace']
                   for s in samples if s['busy']), 'Layout moved during jump'
    if reduced:
        assert samples[-1]['time'] < 400
        assert all(abs(s['y'] - before['y']) < abs(after['y'] - before['y']) + .1 for s in samples)
    else:
        assert 760 <= samples[-1]['time'] < 1100, samples[-1]['time']
        assert all(abs(s['x']-before['x']) < .1 and abs(s['y']-before['y']) < .1
                   for s in samples if s['time'] < 60), 'Anticipation moved away from marker'
        # Use actual path progress, including when resize moves the route.
        transformed_flight = [
            s for s in samples
            if 0 < s['pathProgress'] < 100
            and abs(s['scaleY'] - 1) > .0001
        ]
        assert not transformed_flight, transformed_flight[:3]
        if not resize:
            # The landing squash changes the transformed bounding-box centre while
            # the motion-path anchor remains fixed at the target. Once the flight
            # reaches 100%, it must stay there until the path is cleared and snapped.
            landing_start = next(
                (index for index, sample in enumerate(samples)
                 if sample['busy'] and sample['pathProgress'] >= 99.9),
                None,
            )
            assert landing_start is not None, 'Motion path did not reach its target'
            assert all(
                sample['pathProgress'] >= 99.9
                for sample in samples[landing_start:] if sample['busy']
            ), 'Landing moved away from target'
        assert min(s['y'] for s in samples) < min(before['y'], after['y']) - 18, 'No jump arc'
        if not resize:
            distinct_positions = len({(round(s['x'], 2), round(s['y'], 2)) for s in samples})
            # Headless Edge may throttle requestAnimationFrame to about 30 fps.
            assert len(samples) >= 20 and distinct_positions >= 18, (len(samples), distinct_positions)
            velocities = [
                ((b['x']-a['x'])**2 + (b['y']-a['y'])**2)**.5 / (b['time']-a['time'])
                for a, b in zip(samples, samples[1:]) if b['time'] - a['time'] >= 8
            ]
            assert max(velocities) < .8, ('Container position jumped between animation frames', max(velocities))
    print(f"PASS {before['step']} -> {target}; rapid={rapid}, resize={resize}, reduced={reduced}")
    return after


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.route('**/api/auth/register', lambda route: route.fulfill(
        status=201,
        content_type='application/json',
        body='{"ok":true,"redirect":"/dashboard"}',
    ))
    errors = []
    route_requests = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: route_requests.append(request.url)
            if '/images/registration/route/' in request.url else None)
    page.goto(URL)
    page.wait_for_function("document.querySelectorAll('.register-route-character img').length === 1 && document.querySelector('.register-route-character__sprite').naturalWidth === 221 && document.querySelector('[data-route-character-mood]').dataset.routeCharacterMood === 'idle'")
    page.wait_for_timeout(100)
    selected_input = page.locator('.role-card input:checked')
    assert selected_input.evaluate('e => !e.matches(":focus-visible")')
    selected_surface = page.locator('.role-card input:checked + .role-card__surface')
    assert selected_surface.evaluate('e => getComputedStyle(e).outlineStyle') == 'none'
    selected_input.press('Space')
    assert selected_input.evaluate('e => e.matches(":focus-visible")')
    assert selected_surface.locator('.role-card__indicator').evaluate(
        'e => getComputedStyle(e).boxShadow != "none"'
    )
    sprite = page.locator('.register-route-character__sprite')
    assert sprite.evaluate("e => ({opacity:getComputedStyle(e).opacity, transition:getComputedStyle(e).transitionDuration, transitionProperty:getComputedStyle(e).transitionProperty, display:getComputedStyle(e).display, willChange:getComputedStyle(e).willChange, backfaceVisibility:getComputedStyle(e).backfaceVisibility, width:e.getAttribute('width'), height:e.getAttribute('height'), naturalWidth:e.naturalWidth, naturalHeight:e.naturalHeight})") == {
        'opacity': '1', 'transition': '0s', 'transitionProperty': 'none', 'display': 'block',
        'willChange': 'auto', 'backfaceVisibility': 'visible',
        'width': '221', 'height': '210', 'naturalWidth': 221, 'naturalHeight': 210,
    }
    assert page.locator('.register-route-character').evaluate("e => ({opacity:getComputedStyle(e).opacity, transitionDuration:getComputedStyle(e).transitionDuration, willChange:getComputedStyle(e).willChange, backfaceVisibility:getComputedStyle(e).backfaceVisibility})") == {
        'opacity': '1', 'transitionDuration': '0s', 'willChange': 'auto', 'backfaceVisibility': 'visible',
    }
    page.evaluate("window.initialRouteSprite = document.querySelector('.register-route-character__sprite')")
    cdp = page.context.new_cdp_session(page)
    cdp.send('Network.enable')
    cdp.send('Network.setCacheDisabled', {'cacheDisabled': True})
    route_requests.clear()
    at_step(page, 1)
    jump(page, '.role-form', 2, rapid=True)
    assert page.evaluate("window.initialRouteSprite === document.querySelector('.register-route-character__sprite')")
    assert not route_requests, route_requests
    jump(page, '[data-register-progress="1"] > span', 1, rapid=True)
    jump(page, '.role-form', 2)
    page.locator('[data-name-form] button[type=submit]').click()
    assert page.locator('#register-name').get_attribute('aria-invalid') == 'true'
    at_step(page, 2)
    page.locator('#register-name').fill('Анна')
    jump(page, '[data-name-form]', 3)
    page.reload()
    page.wait_for_function("document.querySelector('.register-route-character__sprite').naturalWidth === 221 && document.querySelector('[data-route-character-mood]').dataset.routeCharacterMood === 'idle'")
    route_requests.clear()
    first = at_step(page, 3)
    page.wait_for_timeout(100)
    assert at_step(page, 3)['x'] == first['x']
    page.locator('#register-email').fill('anna@example.test')
    jump(page, '[data-email-form]', 4)
    page.locator('#register-password').fill('Testpass123')
    page.locator('#register-password-confirmation').fill('Testpass123')
    jump(page, '[data-password-form]', 5, rapid=True)
    page.wait_for_timeout(900)
    at_step(page, 5)
    assert page.locator('[data-register-success-title]').evaluate(
        'e => getComputedStyle(e).outlineStyle == "none"'
    )
    flag = page.locator('.register-progress__flag')
    assert flag.locator('path').evaluate(
        'e => getComputedStyle(e).stroke == "rgb(24, 60, 255)"'
    )
    assert flag.evaluate('e => getComputedStyle(e).animationName.includes("register-flag-sway")')
    page.screenshot(path=str(QA / 'success-desktop.png'))
    jump(page, '[data-register-progress="4"] > span', 4)
    page.wait_for_timeout(360)
    assert flag.locator('path').evaluate(
        'e => getComputedStyle(e).stroke == "rgb(213, 218, 228)"'
    )
    assert flag.evaluate('e => getComputedStyle(e).animationName == "none"')
    jump(page, '[data-register-progress="3"] > span', 3, resize=True)
    jump(page, '[data-register-progress="2"] > span', 2)
    page.locator('#register-name').fill('Анна')
    jump(page, '[data-name-form]', 3)
    page.screenshot(path=str(QA / 'mobile.png'), full_page=True)
    for width in (320, 375, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        page.wait_for_timeout(80)
        at_step(page, 3)
        # Removing the decorative layer must not move existing content.
        geometry = page.evaluate(SAMPLE)
        page.locator('.register-route-character').evaluate("e => e.style.display = 'none'")
        assert page.locator('.register-progress').bounding_box()['height'] == geometry['route']['height']
        assert page.locator('.register-workspace').bounding_box()['y'] == geometry['workspace']['y']
        page.locator('.register-route-character').evaluate("e => e.style.removeProperty('display')")
    page.emulate_media(reduced_motion='reduce')
    jump(page, '[data-register-progress="2"] > span', 2, reduced=True)
    jump(page, '[data-name-form]', 3, reduced=True)
    assert not route_requests, route_requests
    assert not errors, errors
    browser.close()
    print('PASS reload, validation, alignment, fixed size, no sprite flicker, responsive, overlay layout, success hold, browser console')
