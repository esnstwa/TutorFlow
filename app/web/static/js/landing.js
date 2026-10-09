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
      y: -10,
      rotation: 0.8,
      duration: 2.8,
      ease: "sine.inOut",
      repeat: -1,
      yoyo: true,
    });
  }

  function initStory({ gsap, story, stage, states, debugEmotion }) {
    story.classList.add("is-animated");
    const chapters = [...story.querySelectorAll("[data-chapter]")];
    const copies = chapters.map(chapter => chapter.querySelector(".chapter-copy"));
    const character = story.querySelector(".augustin-position");
    const featureElements = new Map(
      [...story.querySelectorAll("[data-feature-elements]")]
        .map(element => [element.dataset.featureElements, element]),
    );
    const idle = initIdleAnimation(gsap, stage);
    let scrollTween = null;
    let isDisposed = false;

    function syncIdleAtProgress(progress) {
      if (isDisposed) return;
      const storyPosition = progress * (chapters.length - 1);
      const isStableState = Math.abs(storyPosition - Math.round(storyPosition)) < 0.01;

      if (isStableState && !scrollTween) {
        idle.resume();
      } else {
        idle.pause();
      }
    }

    gsap.set(copies.slice(1), { opacity: 0, y: 24 });
    gsap.set([...featureElements.values()], { opacity: 0, y: 20, scale: 0.98 });

    const timeline = gsap.timeline({
      defaults: { ease: "power1.inOut" },
      scrollTrigger: {
        id: "augustin-story",
        trigger: story,
        start: "top top",
        end: "bottom bottom",
        scrub: 0.06,
        invalidateOnRefresh: true,
        onUpdate(self) {
          syncIdleAtProgress(self.progress);
        },
      },
    });

    const labels = ["hero", "problem", "focused", "action", "result"];
    const timelineClock = { progress: 0 };
    timeline.to(timelineClock, {
      progress: 1,
      duration: labels.length - 1,
      ease: "none",
    }, 0);
    timeline.addLabel(labels[0], 0);

    chapters.slice(1).forEach((chapter, offset) => {
      const index = offset + 1;
      const start = index - 0.92;
      const changeAt = start + 0.34;
      const previousEmotion = chapters[index - 1].dataset.chapter;
      const nextEmotion = chapter.dataset.chapter;
      const previousElements = featureElements.get(previousEmotion);
      const nextElements = featureElements.get(nextEmotion);

      timeline.addLabel(labels[index], index);
      timeline.to(character, {
        rotation: index * 360,
        duration: 0.72,
        ease: "sine.inOut",
      }, start);
      timeline.to(copies[index - 1], { opacity: 0, y: -12, duration: 0.16 }, start);
      timeline.to(copies[index], { opacity: 1, y: 0, duration: 0.18 }, changeAt);

      if (previousElements) {
        timeline.to(previousElements, { opacity: 0, y: -8, duration: 0.16 }, start);
      }
      if (nextElements) {
        timeline.to(nextElements, { opacity: 1, y: 0, scale: 1, duration: 0.18 }, changeAt);
      }

      if (!debugEmotion) {
        timeline.to(states.get(previousEmotion), {
          opacity: 0,
          duration: 0.14,
          ease: "none",
        }, changeAt);
        timeline.to(states.get(nextEmotion), {
          opacity: 1,
          duration: 0.14,
          ease: "none",
        }, changeAt);
      }
    });

    let requestedIndex = getStepIndex();
    let wheelGestureActive = false;
    let wheelGestureCaptured = false;
    let wheelGestureDirection = 0;
    let wheelGestureTimer = null;
    let touchStartY = null;
    let touchHandled = false;

    function getStepIndex() {
      const progress = timeline.scrollTrigger?.progress || 0;
      return Math.round(progress * (chapters.length - 1));
    }

    function animateToStep(targetIndex) {
      const trigger = timeline.scrollTrigger;
      if (!trigger || isDisposed) return;
      idle.pause();

      const stepDistance = (trigger.end - trigger.start) / (chapters.length - 1);
      const targetY = trigger.start + stepDistance * targetIndex;
      const distanceInSteps = Math.abs(targetY - window.scrollY) / stepDistance;
      const duration = Math.min(0.6, 0.42 + Math.max(0, distanceInSteps - 1) * 0.08);
      const scrollPosition = { y: window.scrollY };

      const previousTween = scrollTween;
      scrollTween = null;
      previousTween?.kill();

      let tween = null;
      tween = gsap.to(scrollPosition, {
        y: targetY,
        duration,
        ease: "power2.inOut",
        overwrite: true,
        onUpdate: () => window.scrollTo(0, scrollPosition.y),
        onComplete: () => {
          if (scrollTween !== tween) return;
          scrollTween = null;
          syncIdleAtProgress(trigger.progress);
        },
        onInterrupt: () => {
          if (scrollTween !== tween) return;
          scrollTween = null;
          syncIdleAtProgress(trigger.progress);
        },
      });
      scrollTween = tween;
    }

    function requestStep(direction) {
      const baseIndex = scrollTween ? requestedIndex : getStepIndex();
      const nextIndex = Math.max(0, Math.min(chapters.length - 1, baseIndex + direction));
      if (nextIndex === baseIndex) return false;

      requestedIndex = nextIndex;
      animateToStep(requestedIndex);
      return true;
    }

    function isInsideStory() {
      const trigger = timeline.scrollTrigger;
      return trigger && window.scrollY >= trigger.start - 1 && window.scrollY <= trigger.end + 1;
    }

    function onWheel(event) {
      if (!isInsideStory() || Math.abs(event.deltaY) < 2) return;
      const direction = event.deltaY > 0 ? 1 : -1;
      const isNewGesture = !wheelGestureActive || direction !== wheelGestureDirection;

      window.clearTimeout(wheelGestureTimer);
      wheelGestureTimer = window.setTimeout(() => {
        wheelGestureActive = false;
        wheelGestureCaptured = false;
      }, 100);

      if (!isNewGesture) {
        if (wheelGestureCaptured) event.preventDefault();
        return;
      }

      wheelGestureActive = true;
      wheelGestureDirection = direction;
      wheelGestureCaptured = requestStep(direction);
      if (wheelGestureCaptured) event.preventDefault();
    }

    function onTouchStart(event) {
      touchStartY = event.touches[0]?.clientY ?? null;
      touchHandled = false;
    }

    function onTouchMove(event) {
      if (!isInsideStory() || touchStartY === null || touchHandled) return;
      const currentY = event.touches[0]?.clientY;
      if (currentY === undefined) return;

      const delta = touchStartY - currentY;
      if (Math.abs(delta) < 12) return;
      if (requestStep(delta > 0 ? 1 : -1)) {
        touchHandled = true;
        event.preventDefault();
      }
    }

    function onTouchEnd() {
      touchStartY = null;
      touchHandled = false;
    }

    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onTouchEnd, { passive: true });

    return () => {
      isDisposed = true;
      window.clearTimeout(wheelGestureTimer);
      const activeTween = scrollTween;
      scrollTween = null;
      activeTween?.kill();
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
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
      animated: "(min-width: 768px) and (min-height: 640px) and (prefers-reduced-motion: no-preference)",
      reduced: "(prefers-reduced-motion: reduce)",
      short: "(max-height: 639px)",
    }, context => {
      if (!context.conditions.animated || context.conditions.reduced || context.conditions.short) {
        initReducedMotion(story, stage, states, debugEmotion);
        return undefined;
      }

      return initStory({ gsap, story, stage, states, debugEmotion });
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
