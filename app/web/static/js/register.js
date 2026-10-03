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
  const emailForm = document.querySelector("[data-email-form]");
  const emailInput = document.querySelector("#register-email");
  const emailError = document.querySelector("[data-email-error]");
  const emailField = emailInput?.closest(".email-form__field");
  const storageKey = "tutorflow.registration";
  const invalidNameCharacterPattern = /[^А-Яа-яЁё-]/;
  const invalidNameCharactersPattern = /[^А-Яа-яЁё-]/g;
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const maximumNameLength = 30;
  const maximumEmailLength = 254;
  let registrationState = { role: "teacher", name: "", email: "", step: 1 };

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

  function getEmailValidationError(value) {
    if (!value) return "Введите email";
    if (value.length > maximumEmailLength || !emailPattern.test(value)) {
      return "Введите корректный email";
    }

    return "";
  }

  function setEmailValidity(isValid) {
    emailField?.classList.toggle("is-valid", isValid);
  }

  function showEmailError(message) {
    emailError.textContent = message;
    emailError.classList.add("is-visible");
    emailError.setAttribute("aria-hidden", "false");
    emailInput.setAttribute("aria-invalid", "true");
    setEmailValidity(false);
  }

  function clearEmailError() {
    emailError.textContent = "";
    emailError.classList.remove("is-visible");
    emailError.setAttribute("aria-hidden", "true");
    emailInput.removeAttribute("aria-invalid");
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

    const stepRoutes = new Map([
      [1, `${location.pathname}${location.search}`],
      [2, "#name"],
      [3, "#email"],
      [4, "#step-4"],
      [5, "#step-5"],
    ]);
    history.replaceState(null, "", stepRoutes.get(step) || `${location.pathname}${location.search}`);

    if (step === 2) nameInput?.focus({ preventScroll: true });
    if (step === 3) emailInput?.focus({ preventScroll: true });
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

  if (nameInput && nameError) {
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
    showStep(3);
  });

  if (emailInput && emailError && emailField) {
    registrationState.email = String(registrationState.email || "").trim();
    emailInput.value = registrationState.email;
    setEmailValidity(!getEmailValidationError(registrationState.email));
    saveRegistrationState();

    emailInput.addEventListener("input", () => {
      emailInput.setCustomValidity("");
      clearEmailError();
      registrationState.email = emailInput.value;
      setEmailValidity(!getEmailValidationError(emailInput.value.trim()));
      saveRegistrationState();
    });

    emailInput.addEventListener("blur", () => {
      const email = emailInput.value.trim();
      if (!email) {
        setEmailValidity(false);
        return;
      }

      const validationError = getEmailValidationError(email);
      if (validationError) {
        showEmailError(validationError);
      } else {
        clearEmailError();
        setEmailValidity(true);
      }
    });
  }

  emailForm?.addEventListener("submit", event => {
    event.preventDefault();
    const email = emailInput.value.trim();
    const validationError = getEmailValidationError(email);

    if (validationError) {
      emailInput.value = email;
      emailInput.setCustomValidity("");
      showEmailError(validationError);
      emailInput.focus();
      return;
    }

    emailInput.setCustomValidity("");
    emailInput.value = email;
    registrationState.email = email;
    saveRegistrationState();
    clearEmailError();
    setEmailValidity(true);
    showStep(4);
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
  const hashSteps = new Map([
    ["#name", 2],
    ["#email", 3],
    ["#step-4", 4],
    ["#step-5", 5],
  ]);
  const storedStep = Number(registrationState.step);
  const initialStep = hashSteps.get(location.hash)
    || (Number.isInteger(storedStep) && storedStep >= 1 && storedStep <= 5 ? storedStep : 1);
  showStep(initialStep);
})();
