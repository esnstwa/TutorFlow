/* Decorative route sprite. Marker geometry remains owned by the registration UI. */
window.TutorFlowRouteCharacter = class {
  constructor(route) {
    this.route = route;
    this.layer = route.querySelector('[data-route-character-idle]');
    this.markers = [...route.querySelectorAll('[data-register-progress] > span')];
    this.motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    this.step = 1;
    this.mood = null;
    this.animation = null;
    this.layoutChangedDuringFlight = false;
    this.sprite = document.createElement('img');
    this.sprite.className = 'register-route-character__sprite';
    this.sprite.alt = '';
    this.sprite.width = 221;
    this.sprite.height = 210;
    this.sprite.draggable = false;
    this.layer.append(this.sprite);

    this.frames = new Map();
    this.frameUrls = [];
    const sources = new Map([
      ['idle', this.layer.dataset.routeCharacterIdle],
      ['happy', this.layer.dataset.routeCharacterHappy],
    ]);
    this.ready = Promise.all([...sources].map(async ([name, path]) => {
      const response = await fetch(path, { cache: 'force-cache' });
      if (!response.ok) throw new Error(`Unable to preload route character: ${name}`);
      const url = URL.createObjectURL(await response.blob());
      const image = new Image();
      image.src = url;
      await image.decode();
      this.frames.set(name, image);
      this.frameUrls.push(url);
    })).then(() => this.setMood(this.step === this.markers.length ? 'happy' : 'idle'));
    window.addEventListener('pagehide', () => {
      this.frameUrls.forEach(url => URL.revokeObjectURL(url));
    }, { once: true });

    this.observer = new ResizeObserver(() => this.handleLayoutChange());
    this.observer.observe(route);
    this.markers.forEach(marker => this.observer.observe(marker));
    this.observer.observe(this.layer);
    window.addEventListener('resize', () => this.handleLayoutChange());
    document.fonts?.ready.then(() => this.handleLayoutChange());
  }

  setMood(mood) {
    if (this.mood === mood) return;
    const frame = this.frames.get(mood);
    if (!frame?.complete || !frame.naturalWidth) return;
    this.sprite.src = frame.src;
    this.mood = mood;
    this.layer.dataset.routeCharacterMood = mood;
  }

  measure() {
    const route = this.route.getBoundingClientRect();
    const characterStyle = getComputedStyle(this.layer);
    const characterHeight = parseFloat(characterStyle.height) || 0;
    const characterWidth = parseFloat(characterStyle.width) || 0;
    const visualBottomFromCenter = characterHeight * (200 / 210 - .5);
    const gap = 9;
    return {
      characterHeight,
      characterWidth,
      points: this.markers.map(marker => {
        const bounds = marker.getBoundingClientRect();
        return {
          x: bounds.left + bounds.width / 2 - route.left,
          y: bounds.top - route.top - gap - visualBottomFromCenter,
        };
      }),
    };
  }

  transform(point, geometry, scaleY = 1) {
    const x = point.x - geometry.characterWidth / 2;
    const y = point.y - geometry.characterHeight / 2;
    const translate = `translate(${x}px, ${y}px)`;
    return scaleY === 1 ? translate : `${translate} scaleY(${scaleY})`;
  }

  handleLayoutChange() {
    if (this.animation) {
      this.layoutChangedDuringFlight = true;
      return;
    }
    this.snap(this.step);
  }

  snap(step) {
    this.step = step;
    if (this.animation) return;
    this.clearMotionPath();
    const geometry = this.measure();
    this.layer.style.transform = this.transform(geometry.points[step - 1], geometry);
  }

  clearMotionPath() {
    this.layer.style.removeProperty('offset-path');
    this.layer.style.removeProperty('offset-anchor');
    this.layer.style.removeProperty('offset-rotate');
    this.layer.style.removeProperty('offset-distance');
  }

  flight(from, to, anticipationDuration, flightDuration, landingDuration) {
    const duration = anticipationDuration + flightDuration + landingDuration;
    const anticipationEnd = anticipationDuration / duration;
    const flightEnd = (anticipationDuration + flightDuration) / duration;
    const horizontalDistance = Math.abs(to.x - from.x);
    const verticalDistance = Math.abs(to.y - from.y);
    const jumpHeight = this.motion.matches
      ? 0 : Math.min(44, Math.max(22, horizontalDistance * .22 + verticalDistance * .45));
    const midpointX = (from.x + to.x) / 2;
    const peakY = Math.min(from.y, to.y) - jumpHeight;
    const controlY = peakY * 2 - (from.y + to.y) / 2;
    const path = `path("M ${from.x} ${from.y} Q ${midpointX} ${controlY} ${to.x} ${to.y}")`;
    const keyframes = [];

    if (anticipationDuration) {
      keyframes.push(
        { offset: 0, offsetDistance: '0%', transform: 'scaleY(1)' },
        { offset: anticipationEnd * .55, offsetDistance: '0%', transform: 'scaleY(.95)' },
        { offset: anticipationEnd * .84, offsetDistance: '0%', transform: 'scaleY(1.04)' },
        {
          offset: anticipationEnd,
          offsetDistance: '0%',
          transform: 'scaleY(1)',
          easing: 'cubic-bezier(.3, .42, .7, .58)',
        },
      );
    } else {
      keyframes.push({
        offset: 0,
        offsetDistance: '0%',
        transform: 'scaleY(1)',
        easing: 'cubic-bezier(.3, .42, .7, .58)',
      });
    }

    keyframes.push({
      offset: flightEnd,
      offsetDistance: '100%',
      transform: 'scaleY(1)',
    });

    if (landingDuration) {
      const landingSpan = 1 - flightEnd;
      keyframes.push(
        { offset: flightEnd + landingSpan * .38, offsetDistance: '100%', transform: 'scaleY(.96)' },
        { offset: flightEnd + landingSpan * .7, offsetDistance: '100%', transform: 'scaleY(1.01)' },
        { offset: 1, offsetDistance: '100%', transform: 'scaleY(1)' },
      );
    }
    return { keyframes, path };
  }

  async jump(to) {
    await this.ready;
    const from = this.step;
    if (from === to || this.animation) return;
    if (from === this.markers.length && to < from) this.setMood('idle');

    const geometry = this.measure();
    const start = geometry.points[from - 1];
    const target = geometry.points[to - 1];
    const anticipationDuration = this.motion.matches ? 0 : 75;
    const flightDuration = this.motion.matches ? 240 : 660;
    const landingDuration = this.motion.matches ? 0 : 110;
    const duration = anticipationDuration + flightDuration + landingDuration;
    const flight = this.flight(
      start, target, anticipationDuration, flightDuration, landingDuration,
    );

    this.layoutChangedDuringFlight = false;
    this.layer.style.offsetPath = flight.path;
    this.layer.style.offsetAnchor = 'center';
    this.layer.style.offsetRotate = '0deg';
    this.layer.style.offsetDistance = '0%';
    this.layer.style.transform = 'none';
    this.animation = this.layer.animate(flight.keyframes, {
      duration,
      easing: 'linear',
      fill: 'forwards',
    });
    try {
      await this.animation.finished;
    } finally {
      this.animation.cancel();
      this.animation = null;
      this.clearMotionPath();
      this.layer.style.transform = this.transform(target, geometry);
    }

    this.step = to;
    if (this.layoutChangedDuringFlight) this.snap(to);
    if (to === this.markers.length) this.setMood('happy');
  }
};
