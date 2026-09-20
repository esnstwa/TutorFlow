(() => {
  "use strict";

  function getAugustinStates(stage) {
    return new Map(
      [...stage.querySelectorAll(".augustin-state")].map(image => [image.dataset.emotion, image]),
    );
  }

  function setAugustinEmotion(stage, states, emotion) {
    stage.dataset.emotion = emotion;
    states.forEach((image, name) => image.classList.toggle("is-active", name === emotion));
  }

  function initIdleAnimation(gsap, stage) {
    return gsap.to(stage, {
      y: -5,
      rotation: 0.5,
      duration: 3,
      ease: "sine.inOut",
      repeat: -1,
      yoyo: true,
    });
  }

  function getPoses(mode) {
    if (mode === "desktop") {
      return [
        { x: 0, y: 0, rotation: 0, scale: 1 },
        { x: -0.31, y: 0.10, rotation: -7, scale: 0.94 },
        { x: 0.19, y: -0.12, rotation: 5, scale: 0.97 },
        { x: -0.27, y: 0.01, rotation: -2, scale: 1 },
        { x: -0.07, y: -0.23, rotation: 3, scale: 0.90 },
      ];
    }

    const amplitude = mode === "tablet" ? 0.07 : 0.025;
    return [
      { x: 0, y: 0, rotation: 0, scale: 1 },
      { x: -amplitude, y: 0.015, rotation: -3, scale: 0.97 },
      { x: amplitude, y: -0.02, rotation: 3, scale: 0.98 },
      { x: -amplitude / 2, y: 0, rotation: -1, scale: 1 },
      { x: 0, y: -0.02, rotation: 2, scale: 1.03 },
    ];
  }

  function initStory({ gsap, story, stage, states, debugEmotion, mode }) {
    story.classList.add("is-animated");
    const chapters = [...story.querySelectorAll("[data-chapter]")];
    const copies = chapters.map(chapter => chapter.querySelector(".chapter-copy"));
    const character = story.querySelector(".augustin-position");
    const poses = getPoses(mode);
    const idle = initIdleAnimation(gsap, stage);
    let idleStopped = false;

    gsap.set(copies.slice(1), { opacity: 0, y: 24 });

    const timeline = gsap.timeline({
      defaults: { ease: "power1.inOut" },
      scrollTrigger: {
        id: "augustin-story",
        trigger: story,
        start: "top top",
        end: "bottom bottom",
        scrub: 0.65,
        invalidateOnRefresh: true,
        onUpdate(self) {
          if (self.progress > 0 && !idleStopped) {
            idleStopped = true;
            idle.pause();
            gsap.to(stage, { y: 0, rotation: 0, duration: 0.3, overwrite: true });
          }
        },
      },
    });

    timeline.addLabel("hero", 0);
    const labels = ["hero", "problem", "thinking", "solution", "final"];
    chapters.slice(1).forEach((chapter, offset) => {
      const index = offset + 1;
      const start = index - 0.82;
      const pose = poses[index];

      timeline.addLabel(labels[index], index);
      timeline.to(character, {
        x: () => pose.x * window.innerWidth,
        y: () => pose.y * window.innerHeight,
        rotation: pose.rotation,
        scale: pose.scale,
        duration: 0.66,
      }, start);
      timeline.to(copies[index - 1], { opacity: 0, y: -18, duration: 0.22 }, start);
      timeline.to(copies[index], { opacity: 1, y: 0, duration: 0.3 }, index - 0.45);

      if (!debugEmotion) {
        timeline.to(states.get(chapters[index - 1].dataset.chapter), {
          opacity: 0,
          duration: 0.12,
          ease: "none",
        }, index - 0.50);
        timeline.to(states.get(chapter.dataset.chapter), {
          opacity: 1,
          duration: 0.12,
          ease: "none",
        }, index - 0.50);
      }
    });

    timeline.fromTo(
      story.querySelector(".story-progress__line"),
      { scaleX: 0 },
      { scaleX: 1, duration: 4, ease: "none" },
      0,
    );

    return () => {
      idle.kill();
      story.classList.remove("is-animated");
    };
  }

  function initReducedMotion(story, stage, states, debugEmotion) {
    story.classList.remove("is-animated");
    setAugustinEmotion(stage, states, debugEmotion || "neutral");
  }

  function initLanding() {
    const story = document.querySelector("[data-story]");
    const stage = document.querySelector("[data-augustin-stage]");
    if (!story || !stage) return;

    const states = getAugustinStates(stage);
    const requested = new URLSearchParams(window.location.search).get("augustin");
    const debugEmotion = states.has(requested) ? requested : null;
    setAugustinEmotion(stage, states, debugEmotion || "neutral");

    const { gsap, ScrollTrigger } = window;
    if (!gsap || !ScrollTrigger) return;
    gsap.registerPlugin(ScrollTrigger);

    const media = gsap.matchMedia();
    media.add({
      desktop: "(min-width: 1024px)",
      tablet: "(min-width: 768px) and (max-width: 1023px)",
      mobile: "(max-width: 767px)",
      reduced: "(prefers-reduced-motion: reduce)",
      short: "(max-height: 639px)",
    }, context => {
      if (context.conditions.reduced || context.conditions.short) {
        initReducedMotion(story, stage, states, debugEmotion);
        return undefined;
      }

      const mode = context.conditions.desktop
        ? "desktop"
        : context.conditions.tablet
          ? "tablet"
          : "mobile";
      return initStory({ gsap, story, stage, states, debugEmotion, mode });
    });

    const refresh = () => ScrollTrigger.refresh();
    const onPageHide = event => {
      if (event.persisted) return;
      media.revert();
      window.removeEventListener("pageshow", refresh);
      window.removeEventListener("pagehide", onPageHide);
    };
    window.addEventListener("pageshow", refresh);
    window.addEventListener("pagehide", onPageHide);
  }

  initLanding();
})();
