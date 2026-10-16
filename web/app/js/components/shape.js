export const shape = (kind, large = false) =>
  `<span class="shape shape--${kind}${large ? " shape--lg" : ""}" aria-hidden="true"></span>`;
