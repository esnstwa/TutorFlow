(() => {
  "use strict";

  const cards = [...document.querySelectorAll(".role-card")];
  if (!cards.length) return;

  const steps = [...document.querySelectorAll("[data-register-step]")];
  const progressItems = [...document.querySelectorAll("[data-register-progress]")];
  const roleForm = document.querySelector(".role-form");
  const nameForm = document.querySelector("[data-name-form]");
  const nameInput = document.querySelector("#register-name");
  const nameError = document.querySelector("[data-name-error]");
  const nameSuccess = document.querySelector("[data-name-success]");
  const nameSuccessText = document.querySelector("[data-name-success-text]");
  const storageKey = "tutorflow.registration";
  const invalidNameCharacterPattern = /[^А-Яа-яЁё-]/;
  const invalidNameCharactersPattern = /[^А-Яа-яЁё-]/g;
  const maximumNameLength = 30;
  let registrationState = { role: "teacher", name: "", step: 1 };

  try {
    registrationState = { ...registrationState, ...JSON.parse(sessionStorage.getItem(storageKey) || "{}") };
  } catch {
    // Continue with defaults when session storage is unavailable or malformed.
  }

  function saveRegistrationState() {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(registrationState));
    } catch {
      // Browser storage is an enhancement; the current registration still works without it.
    }
  }

  function filterNameInput(value) {
    const allowedCharacters = value.trim().replace(invalidNameCharactersPattern, "");
    let filteredName = "";
    let hasHyphen = false;

    for (const character of allowedCharacters) {
      if (character === "-") {
        if (!filteredName || hasHyphen) continue;
        hasHyphen = true;
      }
      filteredName += character;
    }

    return filteredName.slice(0, maximumNameLength);
  }

  function getNameValidationError(value) {
    if (!value) return "Введите имя";
    if (invalidNameCharacterPattern.test(value)) return "Используйте только русские буквы";
    if (value.length < 2 || value.length > maximumNameLength) {
      return "Имя должно содержать от 2 до 30 символов";
    }

    if (value.includes("-")) {
      const parts = value.split("-");
      if (parts.length !== 2 || parts.some(part => part.length < 2)) {
        return "Дефис можно использовать только между частями имени";
      }
    }

    return "";
  }

  function showNameError(message) {
    nameError.textContent = message;
    nameError.classList.add("is-visible");
    nameError.setAttribute("aria-hidden", "false");
    nameInput.setAttribute("aria-invalid", "true");
  }

  function clearNameError() {
    nameError.textContent = "";
    nameError.classList.remove("is-visible");
    nameError.setAttribute("aria-hidden", "true");
    nameInput.removeAttribute("aria-invalid");
  }

  function hideNameSuccess() {
    nameSuccess.classList.remove("is-visible");
    nameSuccess.setAttribute("aria-hidden", "true");
  }

  function showStep(step) {
    registrationState.step = step;
    saveRegistrationState();

    steps.forEach(element => {
      element.hidden = Number(element.dataset.registerStep) !== step;
    });

    progressItems.forEach(item => {
      const itemStep = Number(item.dataset.registerProgress);
      const isComplete = itemStep < step;
      const node = item.querySelector(":scope > span");
      item.classList.toggle("is-complete", isComplete);
      item.classList.toggle("is-active", itemStep === step);
      if (itemStep === step) {
        item.setAttribute("aria-current", "step");
      } else {
        item.removeAttribute("aria-current");
      }

      if (isComplete) {
        node?.setAttribute("role", "button");
        node?.setAttribute("tabindex", "0");
        node?.setAttribute("aria-label", `Вернуться к шагу ${itemStep}`);
      } else {
        node?.removeAttribute("role");
        node?.removeAttribute("tabindex");
        node?.removeAttribute("aria-label");
      }
    });

    if (step === 2) {
      history.replaceState(null, "", "#name");
      nameInput?.focus({ preventScroll: true });
    } else {
      history.replaceState(null, "", `${location.pathname}${location.search}`);
    }
  }

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
    const input = card.querySelector('input[name="role"]');
    input?.addEventListener("change", () => {
      syncLevitation();
      registrationState.role = input.value;
      saveRegistrationState();
    });
  });

  roleForm?.addEventListener("submit", event => {
    event.preventDefault();
    const selectedRole = roleForm.querySelector('input[name="role"]:checked');
    if (!selectedRole) return;

    registrationState.role = selectedRole.value;
    saveRegistrationState();
    showStep(2);
  });

  progressItems.forEach(item => {
    const node = item.querySelector(":scope > span");
    const returnToStep = () => {
      const itemStep = Number(item.dataset.registerProgress);
      if (itemStep >= registrationState.step) return;
      showStep(itemStep);
    };

    node?.addEventListener("click", returnToStep);
    node?.addEventListener("keydown", event => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      returnToStep();
    });
  });

  const savedRole = cards
    .map(card => card.querySelector('input[name="role"]'))
    .find(input => input?.value === registrationState.role);
  if (savedRole) savedRole.checked = true;

  if (nameInput && nameError && nameSuccess && nameSuccessText) {
    registrationState.name = filterNameInput(String(registrationState.name || ""));
    nameInput.value = registrationState.name;
    saveRegistrationState();

    nameInput.addEventListener("input", () => {
      const enteredName = nameInput.value;
      const cursorPosition = nameInput.selectionStart ?? nameInput.value.length;
      const filteredCursorValue = filterNameInput(nameInput.value.slice(0, cursorPosition));
      const filteredName = filterNameInput(nameInput.value);
      const enteredHyphensCount = [...enteredName].filter(character => character === "-").length;
      let inputError = "";

      if (invalidNameCharacterPattern.test(enteredName)) {
        inputError = "Используйте только русские буквы";
      } else if (enteredName.length > maximumNameLength) {
        inputError = "Имя должно содержать от 2 до 30 символов";
      } else if (enteredName.startsWith("-") || enteredHyphensCount > 1) {
        inputError = "Дефис можно использовать только между частями имени";
      }

      if (nameInput.value !== filteredName) {
        nameInput.value = filteredName;
        nameInput.setSelectionRange(filteredCursorValue.length, filteredCursorValue.length);
      }

      nameInput.setCustomValidity("");
      if (inputError) {
        showNameError(inputError);
      } else {
        clearNameError();
      }
      hideNameSuccess();
      registrationState.name = filteredName;
      saveRegistrationState();
    });
  }

  nameForm?.addEventListener("submit", event => {
    event.preventDefault();
    const name = nameInput.value.trim();
    const validationError = getNameValidationError(name);

    if (validationError) {
      nameInput.value = name;
      hideNameSuccess();
      nameInput.setCustomValidity("");
      showNameError(validationError);
      nameInput.focus();
      return;
    }

    nameInput.setCustomValidity("");
    nameInput.value = name;
    registrationState.name = name;
    saveRegistrationState();
    clearNameError();
    nameSuccessText.textContent = `Отлично, ${name}. Идём дальше.`;
    nameSuccess.classList.add("is-visible");
    nameSuccess.setAttribute("aria-hidden", "false");
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
  showStep(location.hash === "#name" || registrationState.step === 2 ? 2 : 1);
})();
