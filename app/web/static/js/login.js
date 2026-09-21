(() => {
  "use strict";

  function initPasswordToggle() {
    const toggle = document.querySelector("[data-password-toggle]");
    const password = document.querySelector("#login-password");
    if (!toggle || !password) return;

    const visibleIcon = toggle.querySelector("[data-icon-password-visible]");
    const hiddenIcon = toggle.querySelector("[data-icon-password-hidden]");

    toggle.addEventListener("click", () => {
      const isVisible = password.type === "text";
      password.type = isVisible ? "password" : "text";
      toggle.setAttribute("aria-pressed", String(!isVisible));
      toggle.setAttribute("aria-label", isVisible ? "Показать пароль" : "Скрыть пароль");
      visibleIcon?.toggleAttribute("hidden", isVisible);
      hiddenIcon?.toggleAttribute("hidden", !isVisible);
    });
  }

  function initAugustin() {
    const augustin = document.querySelector("[data-login-augustin]");
    const passwordToggle = document.querySelector("[data-password-toggle]");
    const { gsap } = window;
    if (!augustin || !passwordToggle || !gsap || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const states = new Map(
      [...augustin.querySelectorAll("[data-augustin-state]")].map((image) => [
        image.dataset.augustinState,
        image,
      ]),
    );
    if (!states.has("neutral") || !states.has("closed") || !states.has("peeking")) return;

    const isMobile = window.matchMedia("(max-width: 640px)").matches;
    const placements = isMobile
      ? [
          {
            position: { left: "auto", right: "-3rem", top: "42%", bottom: "auto", transformOrigin: "30% 70%" },
            hidden: { x: -40, y: 0 },
            visible: { x: 6, y: -1 },
            rotation: 2,
          },
          {
            position: { left: "auto", right: "1.5rem", top: "-3.1rem", bottom: "auto", transformOrigin: "50% 75%" },
            hidden: { x: 0, y: 42 },
            visible: { x: 0, y: -6 },
            rotation: 1,
          },
        ]
      : [
          {
            position: { left: "auto", right: "-6rem", top: "38%", bottom: "auto", transformOrigin: "30% 70%" },
            hidden: { x: -76, y: 0 },
            visible: { x: 14, y: -2 },
            rotation: 2,
          },
          {
            position: { left: "auto", right: "2.75rem", top: "-5.5rem", bottom: "auto", transformOrigin: "50% 75%" },
            hidden: { x: 0, y: 72 },
            visible: { x: 0, y: -14 },
            rotation: 1,
          },
        ];
    const passwordPeekPlacement = isMobile
      ? {
          position: { left: "-3rem", right: "auto", top: "46%", bottom: "auto", transformOrigin: "70% 60%" },
          hidden: { x: 40, y: 0 },
          visible: { x: -24, y: -2 },
          rotation: -2,
        }
      : {
          position: { left: "-6rem", right: "auto", top: "43%", bottom: "auto", transformOrigin: "70% 60%" },
          hidden: { x: 76, y: 0 },
          visible: { x: -35, y: -3 },
          rotation: -2,
        };
    let timer = null;
    let timeline = null;
    let isDisposed = false;
    let animationMode = "idle";
    let passwordPeekRequested = false;
    let placementIndex = 0;
    let currentPlacement = placements[placementIndex];

    function showState(name) {
      states.forEach((image, stateName) => {
        image.classList.toggle("is-active", stateName === name);
        gsap.set(image, {
          autoAlpha: stateName === name ? 1 : 0,
          x: 0,
          y: 0,
          scale: 1,
        });
      });
    }

    gsap.set(augustin, {
      ...currentPlacement.position,
      ...currentPlacement.hidden,
      rotation: 1,
      scale: .9,
    });

    function schedule(minimum = 5500, spread = 3000) {
      if (isDisposed || animationMode !== "idle" || passwordPeekRequested) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(peek, minimum + Math.random() * spread);
    }

    function peek() {
      if (isDisposed || animationMode !== "idle" || passwordPeekRequested) return;
      if (document.hidden) {
        schedule(1800, 1600);
        return;
      }

      const availablePlacements = placements.filter((_, index) => index !== placementIndex);
      const placement = availablePlacements[Math.floor(Math.random() * availablePlacements.length)];
      placementIndex = placements.indexOf(placement);
      currentPlacement = placement;
      const horizontalNudge = placement.visible.x >= 0 ? 7 : -7;

      animationMode = "automatic";
      gsap.set(augustin, {
        ...placement.position,
        ...placement.hidden,
        rotation: placement.rotation,
        scale: .9,
      });
      showState("neutral");

      timeline = gsap.timeline({
        onComplete: () => {
          timeline = null;
          animationMode = "idle";
          if (passwordPeekRequested) {
            startPasswordPeek();
          } else {
            schedule();
          }
        },
      });

      timeline
        .to(augustin, { ...placement.visible, rotation: placement.rotation, scale: 1, duration: .9, ease: "power2.out" })
        .to(augustin, { x: placement.visible.x + horizontalNudge, rotation: placement.rotation * 1.5, duration: .4, ease: "sine.inOut" })
        .to(augustin, { x: placement.visible.x - horizontalNudge * .4, rotation: placement.rotation * .7, duration: .48, ease: "sine.inOut" })
        .to(augustin, { x: placement.visible.x, rotation: placement.rotation, duration: .32, ease: "sine.inOut" })
        .to(augustin, { ...placement.hidden, rotation: -placement.rotation, scale: .9, duration: .36, ease: "power3.in", delay: .75 });
    }

    function startPasswordPeek() {
      if (isDisposed) return;

      passwordPeekRequested = false;
      animationMode = "password";
      showState("peeking");
      gsap.set(augustin, {
        ...passwordPeekPlacement.position,
        ...passwordPeekPlacement.hidden,
        rotation: passwordPeekPlacement.rotation,
        scale: .9,
      });

      timeline = gsap.timeline({
        onComplete: () => {
          showState("neutral");
          timeline = null;
          animationMode = "idle";
          schedule(3000, 2000);
        },
      });

      timeline
        .to(augustin, { ...passwordPeekPlacement.visible, scale: 1, duration: .5, ease: "power2.out" })
        .to(augustin, { x: passwordPeekPlacement.visible.x - 4, rotation: -2.8, duration: .18, ease: "sine.inOut" })
        .to(augustin, { x: passwordPeekPlacement.visible.x + 2, y: passwordPeekPlacement.visible.y - 1, rotation: -1.3, duration: .26, ease: "sine.inOut" })
        .to(augustin, { x: passwordPeekPlacement.visible.x, y: passwordPeekPlacement.visible.y, rotation: -2, duration: .18, ease: "sine.inOut" })
        .to(states.get("peeking"), { autoAlpha: 0, y: 1, scale: .992, duration: .24, ease: "sine.inOut" }, "+=.1")
        .fromTo(
          states.get("closed"),
          { autoAlpha: 0, y: -1, scale: 1.008 },
          { autoAlpha: 1, y: 0, scale: 1, duration: .26, ease: "sine.inOut" },
          "<",
        )
        .to(augustin, { x: passwordPeekPlacement.visible.x - 2, y: passwordPeekPlacement.visible.y + 1, rotation: -2.4, duration: .26, ease: "sine.inOut" }, "<")
        .to(augustin, { ...passwordPeekPlacement.hidden, rotation: 2, scale: .9, duration: .3, ease: "power3.in" }, "+=.12");
    }

    function requestPasswordPeek() {
      if (isDisposed || animationMode === "password" || passwordPeekRequested) return;

      passwordPeekRequested = true;
      window.clearTimeout(timer);

      if (animationMode === "automatic" && currentPlacement) {
        timeline?.kill();
        animationMode = "retreat";
        timeline = gsap.timeline({
          onComplete: () => {
            timeline = null;
            startPasswordPeek();
          },
        });
        timeline.to(augustin, {
          ...currentPlacement.hidden,
          rotation: -currentPlacement.rotation,
          scale: .9,
          duration: .4,
          ease: "power2.inOut",
        });
        return;
      }

      if (animationMode === "idle") startPasswordPeek();
    }

    passwordToggle.addEventListener("mouseenter", requestPasswordPeek);
    schedule(2800, 1800);

    window.addEventListener("pagehide", () => {
      isDisposed = true;
      window.clearTimeout(timer);
      timeline?.kill();
      passwordToggle.removeEventListener("mouseenter", requestPasswordPeek);
    }, { once: true });
  }

  initPasswordToggle();
  initAugustin();
})();
