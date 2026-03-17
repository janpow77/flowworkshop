import '@testing-library/jest-dom/vitest';

// jsdom stellt scrollIntoView nicht bereit
Element.prototype.scrollIntoView = () => {};
