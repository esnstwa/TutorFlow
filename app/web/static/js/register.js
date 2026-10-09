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
  const passwordForm = document.querySelector("[data-password-form]");
  const passwordInput = document.querySelector("#register-password");
  const passwordConfirmationInput = document.querySelector("#register-password-confirmation");
  const passwordError = document.querySelector("[data-password-error]");
  const passwordConfirmationError = document.querySelector("[data-password-confirmation-error]");
  const passwordSubmit = passwordForm?.querySelector('button[type="submit"]');
  const registerMain = document.querySelector(".register-main");
  const loginPrompt = document.querySelector("[data-register-login]");
  const completeName = document.querySelector("[data-register-complete-name]");
  const completeDescription = document.querySelector("[data-register-complete-description]");
  const completeCharacter = document.querySelector("[data-register-complete-character]");
  const completeLink = document.querySelector("[data-register-complete]")
    || document.querySelector("[data-register-goto]");
  const passwordRequirements = new Map(
    [...document.querySelectorAll("[data-password-requirement]")].map(element => [
      element.dataset.passwordRequirement,
      element,
    ]),
  );
  const storageKey = "tutorflow.registration";
  const invalidNameCharacterPattern = /[^А-Яа-яЁё-]/;
  const invalidNameCharactersPattern = /[^А-Яа-яЁё-]/g;
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const passwordLetterPattern = /\p{L}/u;
  const passwordDigitPattern = /\d/;
  const maximumNameLength = 30;
  const maximumEmailLength = 254;
  let registrationState = {
    role: "teacher",
    name: "",
    email: "",
    // Passwords live only in the form inputs.
    step: 1,
  };

  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "{}");
    if (saved && typeof saved === "object" && !Array.isArray(saved)) {
      registrationState.role = ["teacher", "student"].includes(saved.role) ? saved.role : "teacher";
      registrationState.name = typeof saved.name === "string" ? saved.name : "";
      registrationState.email = typeof saved.email === "string" ? saved.email.slice(0, maximumEmailLength) : "";
      registrationState.step = Number.isInteger(saved.step) && saved.step >= 1 && saved.step <= 4 ? saved.step : 1;
    }
  } catch {
    // Continue with defaults when session storage is unavailable or malformed.
  }

  // Purge old local copies, including legacy plaintext passwords; never touch invite storage.
  try { localStorage.removeItem(storageKey); } catch { /* Storage may be unavailable. */ }
  let pending = false;
  let registered = false;

  function saveRegistrationState() {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({role: registrationState.role, name: registrationState.name, email: registrationState.email, step: Math.min(registrationState.step, 4)}));
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

  function getPasswordRequirements(value) {
    return {
      length: value.length >= 8,
      letter: passwordLetterPattern.test(value),
      digit: passwordDigitPattern.test(value),
    };
  }

  function isPasswordValid(value) {
    return Object.values(getPasswordRequirements(value)).every(Boolean);
  }

  function setPasswordFieldError(input, error, message) {
    if (!input || !error) return;

    error.textContent = message;
    error.classList.toggle("is-visible", Boolean(message));
    error.setAttribute("aria-hidden", String(!message));
    if (message) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
  }

  function getPasswordConfirmationError(password, confirmation) {
    return confirmation && confirmation !== password ? "Пароли не совпадают" : "";
  }

  function updatePasswordForm() {
    if (!passwordInput || !passwordConfirmationInput || !passwordSubmit) return;

    const password = passwordInput.value;
    const confirmation = passwordConfirmationInput.value;
    const requirements = getPasswordRequirements(password);

    Object.entries(requirements).forEach(([name, isMet]) => {
      passwordRequirements.get(name)?.classList.toggle("is-valid", isMet);
    });

    passwordSubmit.disabled = pending || registered || !(
      password
      && confirmation
      && Object.values(requirements).every(Boolean)
      && password === confirmation
    );
  }

  function initPasswordToggles() {
    document.querySelectorAll("[data-password-toggle]").forEach(toggle => {
      const input = document.getElementById(toggle.getAttribute("aria-controls"));
      if (!input) return;

      const visibleIcon = toggle.querySelector("[data-icon-password-visible]");
      const hiddenIcon = toggle.querySelector("[data-icon-password-hidden]");

      toggle.addEventListener("click", () => {
        const isVisible = input.type === "text";
        input.type = isVisible ? "password" : "text";
        toggle.setAttribute("aria-pressed", String(!isVisible));
        toggle.setAttribute("aria-label", isVisible ? "Показать пароль" : "Скрыть пароль");
        visibleIcon?.toggleAttribute("hidden", isVisible);
        hiddenIcon?.toggleAttribute("hidden", !isVisible);
      });
    });
  }

  function syncCompleteStep() {
    const role = registrationState.role === "student" ? "student" : "teacher";
    const descriptions = {
      student: "Теперь занятия, задания и материалы всегда будут под рукой.",
      teacher: "Теперь можно собрать занятия, учеников и материалы в одном месте.",
    };
    const alternativeText = {
      student: "Августин с рюкзаком и тетрадью",
      teacher: "Августин в очках, с книгой и указкой",
    };

    if (registerMain) registerMain.dataset.completeRole = role;
    if (completeName) completeName.textContent = String(registrationState.name || "").trim();
    if (completeDescription) completeDescription.textContent = descriptions[role];
    if (completeCharacter) {
      completeCharacter.src = completeCharacter.dataset[`${role}Src`];
      completeCharacter.alt = alternativeText[role];
    }
  }

  function allowedStep(requested) {
    if (registered) return 5;
    const maximum = getNameValidationError(registrationState.name) ? 2
      : getEmailValidationError(registrationState.email) ? 3 : 4;
    return Math.min(Math.max(Number.isInteger(requested) ? requested : 1, 1), maximum);
  }

  function showStep(requested, mode = "push") {
    const step = allowedStep(requested);
    registrationState.step = step;
    if (!registered) saveRegistrationState();

    const isCompleteStep = step === 5;
    registerMain?.classList.toggle("is-complete", isCompleteStep);
    if (loginPrompt) loginPrompt.hidden = isCompleteStep;
    if (isCompleteStep) syncCompleteStep();

    steps.forEach(element => {
      element.hidden = Number(element.dataset.registerStep) !== step;
    });

    progressItems.forEach(item => {
      const itemStep = Number(item.dataset.registerProgress);
      const isComplete = !registered && itemStep < step;
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
    const route = stepRoutes.get(step);
    const currentRoute = stepRoutes.get(hashSteps.get(location.hash) || 1);
    if (mode === "replace" || (mode === "sync" && (route !== currentRoute || (location.hash && !hashSteps.has(location.hash))))) {
      history.replaceState(null, "", route);
    } else if (mode === "push" && route !== currentRoute) {
      history.pushState(null, "", route);
    }
    if (step === 1) roleForm.querySelector('input[name="role"]:checked')?.focus({ preventScroll: true });
    if (step === 5) document.querySelector("[data-register-success-title]")?.focus({ preventScroll: true });

    if (step === 2) nameInput?.focus({ preventScroll: true });
    if (step === 3) emailInput?.focus({ preventScroll: true });
    if (step === 4) passwordInput?.focus({ preventScroll: true });
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const routeElement = document.querySelector('.register-progress');
  const routeCharacter = routeElement && window.TutorFlowRouteCharacter
    ? new window.TutorFlowRouteCharacter(routeElement) : null;
  let transitioning = false;

  function transitionStep(step) {
    if (transitioning || step === registrationState.step) return;
    if (!routeCharacter) {
      showStep(step);
      return;
    }

    transitioning = true;
    const wasInert = registerMain?.inert || false;
    if (registerMain) {
      registerMain.inert = true;
      registerMain.setAttribute('aria-busy', 'true');
    }
    return routeCharacter.jump(step).then(() => {
      // Restore interaction before showStep focuses the next field.
      if (registerMain) registerMain.inert = wasInert;
      showStep(step);
      routeCharacter.snap(step);
    }, () => {
      // Decorative animation failures must never block registration navigation.
      if (registerMain) registerMain.inert = wasInert;
      showStep(step);
    }).finally(() => {
      if (registerMain) {
        registerMain.inert = wasInert;
        registerMain.removeAttribute('aria-busy');
      }
      transitioning = false;
    });
  }
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
    if (transitioning) return;
    const selectedRole = roleForm.querySelector('input[name="role"]:checked');
    if (!selectedRole) return;

    registrationState.role = selectedRole.value;
    saveRegistrationState();
    transitionStep(2);
  });

  progressItems.forEach(item => {
    const node = item.querySelector(":scope > span");
    const returnToStep = () => {
      const itemStep = Number(item.dataset.registerProgress);
      if (itemStep >= registrationState.step) return;
      transitionStep(itemStep);
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
    if (transitioning) return;
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
    transitionStep(3);
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
    if (transitioning) return;
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
    transitionStep(4);
  });

  if (passwordInput && passwordConfirmationInput && passwordError && passwordConfirmationError) {
    passwordInput.value = "";
    passwordConfirmationInput.value = "";

    passwordInput.addEventListener("input", () => {
      setPasswordFieldError(passwordInput, passwordError, "");
      if (passwordConfirmationInput.value) {
        setPasswordFieldError(
          passwordConfirmationInput,
          passwordConfirmationError,
          getPasswordConfirmationError(passwordInput.value, passwordConfirmationInput.value),
        );
      }
      saveRegistrationState();
      updatePasswordForm();
    });

    passwordConfirmationInput.addEventListener("input", () => {
      setPasswordFieldError(
        passwordConfirmationInput,
        passwordConfirmationError,
        passwordConfirmationInput.value
          ? getPasswordConfirmationError(passwordInput.value, passwordConfirmationInput.value)
          : "",
      );
      saveRegistrationState();
      updatePasswordForm();
    });

    passwordInput.addEventListener("blur", () => {
      setPasswordFieldError(passwordInput, passwordError, "");
    });

    passwordConfirmationInput.addEventListener("blur", () => {
      setPasswordFieldError(
        passwordConfirmationInput,
        passwordConfirmationError,
        getPasswordConfirmationError(passwordInput.value, passwordConfirmationInput.value),
      );
    });

    updatePasswordForm();
  }

  passwordForm?.addEventListener("submit", async event => {
    event.preventDefault();
    if (transitioning) return;
    const password = passwordInput.value;
    const confirmation = passwordConfirmationInput.value;
    const confirmationValidationError = !confirmation ? "Повторите пароль" : getPasswordConfirmationError(password, confirmation);

    setPasswordFieldError(passwordInput, passwordError, isPasswordValid(password) ? "" : "Пароль: минимум 8 символов, буквы и цифры");
    setPasswordFieldError(
      passwordConfirmationInput,
      passwordConfirmationError,
      confirmationValidationError,
    );

    if (!isPasswordValid(password) || !confirmation || confirmationValidationError) {
      (!isPasswordValid(password) ? passwordInput : passwordConfirmationInput).focus();
      return;
    }

    if (pending || registered) return;
    if (allowedStep(4) !== 4) { showStep(4); return; }
    const submitted = {
      first_name: registrationState.name, last_name: "", email: registrationState.email,
      password, password_confirmation: confirmation, role: registrationState.role,
    };
    pending = true;
    passwordForm.setAttribute("aria-busy", "true");
    updatePasswordForm();
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-TutorFlow-Request": "auth"},
        body: JSON.stringify(submitted),
      });
      const data = await response.json();
      if (!response.ok || data.ok !== true) {
        const fields = data.fields && typeof data.fields === "object" ? data.fields : {};
        const targets = {
          first_name: [2, nameInput, nameError], email: [3, emailInput, emailError],
          password: [4, passwordInput, passwordError],
          password_confirmation: [4, passwordConfirmationInput, passwordConfirmationError],
          role: [1, roleForm.querySelector('input[name="role"]:checked'), document.querySelector("[data-role-error]")],
        };
        let target = null;
        for (const [field, message] of Object.entries(fields)) {
          if (!targets[field] || typeof message !== "string") continue;
          const [step, input, error] = targets[field];
          setPasswordFieldError(input, error, message);
          if (!target || step < target[0]) target = [step, input];
        }
        if (response.status === 409 && !target) {
          showEmailError("Эта почта уже зарегистрирована"); target = [3, emailInput];
        }
        if (target) { showStep(target[0]); target[1]?.focus(); }
        else {
          showStep(4);
          setPasswordFieldError(passwordInput, passwordError,
            typeof data.detail === "string" ? data.detail : "Не удалось создать аккаунт. Попробуйте снова.");
        }
        return;
      }
      registered = true;
      try { sessionStorage.removeItem(storageKey); } catch { /* Storage may be unavailable. */ }
      try { localStorage.removeItem(storageKey); } catch { /* Storage may be unavailable. */ }
      nameInput.value = emailInput.value = passwordInput.value = passwordConfirmationInput.value = "";
      const destination = ["/dashboard", "/student/homework"].includes(data.redirect)
        ? data.redirect : submitted.role === "student" ? "/student/homework" : "/dashboard";
      completeLink?.setAttribute("href", destination);
      await transitionStep(5);
    } catch {
      showStep(4);
      setPasswordFieldError(passwordInput, passwordError, "Проверьте соединение и попробуйте снова.");
    } finally {
      pending = false;
      passwordForm.removeAttribute("aria-busy");
      updatePasswordForm();
    }
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

  initPasswordToggles();
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
  showStep(initialStep, "replace");
  routeCharacter?.snap(registrationState.step);
  const syncRoute = () => {
    showStep(hashSteps.get(location.hash) || 1, "sync");
    routeCharacter?.snap(registrationState.step);
  };
  window.addEventListener("popstate", syncRoute);
  window.addEventListener("hashchange", syncRoute);
})();
