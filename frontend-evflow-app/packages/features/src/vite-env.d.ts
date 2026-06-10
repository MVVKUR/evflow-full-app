declare module '*.svg' {
  const src: string;
  export default src;
}

declare module '*.svg?raw' {
  const src: string;
  export default src;
}

declare module '*.png' {
  const src: number;
  export default src;
}

declare module '*.css';
