(() => {
  "use strict";

  const cards = [...document.querySelectorAll(".role-card")];
  if (!cards.length) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const characterMotions = new Map();
  const settleTimers = new Map();

  function imageFor(card) {
    return card.querySelector(".role-card__image img");
  }

  function clearSettle(image) {
    window.clearTimeout(settleTimers.get(image));
    settleTimers.delete(image);
  }

  function resetImage(image) {
    clearSettle(image);
    characterMotions.get(image)?.cancel();
    characterMotions.delete(image);
    image.style.removeProperty("transition");
    image.style.removeProperty("transform");
    image.style.removeProperty("will-change");
  }

  function playSelectionReaction(image, role) {
    if (reducedMotion.matches || characterMotions.has(image)) return;

    clearSettle(image);
    image.style.transition = "none";
    image.style.transform = "translateY(0) rotate(0)";
    image.style.willChange = "transform";

    const firstTilt = role === "student" ? 2 : -2;
    const animation = image.animate(
      [
        { offset: 0, transform: "translateY(0) rotate(0)", easing: "ease-in-out" },
        { offset: 0.18, transform: `translateY(0) rotate(${firstTilt}deg)`, easing: "ease-in-out" },
        { offset: 0.38, transform: `translateY(0) rotate(${-firstTilt}deg)`, easing: "ease-in-out" },
        { offset: 0.54, transform: "translateY(0) rotate(0)", easing: "ease-in-out" },
        { offset: 0.66, transform: "translateY(-4px) rotate(0)", easing: "ease-in-out" },
        { offset: 0.78, transform: "translateY(0) rotate(0)", easing: "ease-in-out" },
        { offset: 0.89, transform: "translateY(-4px) rotate(0)", easing: "ease-in-out" },
        { offset: 1, transform: "translateY(0) rotate(0)" },
      ],
      {
        duration: 1560,
        easing: "linear",
        iterations: 1,
      },
    );
    characterMotions.set(image, animation);

    animation.finished.then(() => {
      if (characterMotions.get(image) !== animation) return;
      characterMotions.delete(image);
      image.style.removeProperty("transition");
      image.style.removeProperty("transform");
      image.style.removeProperty("will-change");
    }).catch(() => {
      // A role change intentionally cancels the previous character reaction.
    });
  }

  function stopCharacterMotion(image) {
    const animation = characterMotions.get(image);
    if (!animation) return;

    const currentTransform = getComputedStyle(image).transform;
    animation.cancel();
    characterMotions.delete(image);

    image.style.transition = "none";
    image.style.transform = currentTransform === "none" ? "translateY(0)" : currentTransform;
    image.getBoundingClientRect();
    image.style.transition = "transform 220ms ease-in-out";

    requestAnimationFrame(() => {
      image.style.transform = "translateY(0)";
    });

    settleTimers.set(image, window.setTimeout(() => {
      image.style.removeProperty("transition");
      image.style.removeProperty("transform");
      image.style.removeProperty("will-change");
      settleTimers.delete(image);
    }, 240));
  }

  function syncLevitation() {
    cards.forEach(card => {
      const input = card.querySelector('input[name="role"]');
      const image = imageFor(card);
      if (!input || !image) return;

      if (input.checked) {
        playSelectionReaction(image, input.value);
      } else {
        stopCharacterMotion(image);
      }
    });
  }

  cards.forEach(card => {
    card.querySelector('input[name="role"]')?.addEventListener("change", syncLevitation);
  });

  reducedMotion.addEventListener("change", () => {
    if (reducedMotion.matches) {
      cards.forEach(card => resetImage(imageFor(card)));
    } else {
      syncLevitation();
    }
  });

  window.addEventListener("pagehide", () => {
    cards.forEach(card => resetImage(imageFor(card)));
  }, { once: true });

  syncLevitation();
})();
