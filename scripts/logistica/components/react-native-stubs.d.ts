declare module 'react' {
  export const useEffect: (...args: any[]) => any;
  export const useState: (...args: any[]) => any;
  const React: any;
  export default React;
}

declare module 'react-native' {
  export const Text: any;
  export const View: any;
}

declare module 'react/jsx-runtime' {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}
