// 선 아이콘 (stroke = currentColor). 디자인 시스템의 아이콘 한 벌.
type P = { size?: number; className?: string };
const base = (size: number) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true,
});

export const Chevron = ({ size = 16, className }: P) => (
  <svg {...base(size)} strokeWidth={2} className={className}><path d="M9 6l6 6-6 6" /></svg>
);
export const Back = ({ size = 24 }: P) => <svg {...base(size)} strokeWidth={2}><path d="M15 5l-7 7 7 7" /></svg>;
export const Share = ({ size = 22 }: P) => (
  <svg {...base(size)} strokeWidth={1.8}><path d="M12 3v12M7 8l5-5 5 5M5 14v5a2 2 0 002 2h10a2 2 0 002-2v-5" /></svg>
);
export const Clock = ({ size = 22 }: P) => (
  <svg {...base(size)} strokeWidth={1.8}><path d="M12 7v5l3 2" /><circle cx="12" cy="12" r="8.5" /></svg>
);
export const Sliders = ({ size = 22 }: P) => (
  <svg {...base(size)} strokeWidth={1.8}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></svg>
);
export const Check = ({ size = 14, width = 2.4 }: P & { width?: number }) => (
  <svg {...base(size)} strokeWidth={width}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
);
export const Book = ({ size = 22 }: P) => (
  <svg {...base(size)} strokeWidth={1.8}><path d="M4 5.5A1.5 1.5 0 015.5 4H11v16H5.5A1.5 1.5 0 014 18.5zM20 5.5A1.5 1.5 0 0018.5 4H13v16h5.5a1.5 1.5 0 001.5-1.5z" /></svg>
);
export const Drop = ({ size = 22 }: P) => (
  <svg {...base(size)} strokeWidth={1.8}><path d="M12 3c-3 4.5-5 7.4-5 10a5 5 0 0010 0c0-2.6-2-5.5-5-10z" /></svg>
);
export const External = ({ size = 16 }: P) => (
  <svg {...base(size)} strokeWidth={2}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5" /></svg>
);
export const Speaker = ({ size = 22 }: P) => (
  <svg {...base(size)} strokeWidth={1.8}><path d="M4 9v6h4l5 4V5L8 9zM16.5 9a4 4 0 010 6M19 6.5a7.5 7.5 0 010 11" /></svg>
);
export const Kakao = ({ size = 20 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path fill="currentColor" d="M12 4C7 4 3 7.2 3 11.1c0 2.5 1.6 4.7 4.1 5.9l-1 3.6c-.1.3.3.6.6.4l4.2-2.8c.4 0 .7.1 1.1.1 5 0 9-3.2 9-7.2S17 4 12 4z" />
  </svg>
);
export const Info = ({ size = 18 }: P) => (
  <svg {...base(size)} strokeWidth={1.8}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 7.6v.4" /></svg>
);
export const Close = ({ size = 20 }: P) => <svg {...base(size)} strokeWidth={2}><path d="M6 6l12 12M18 6L6 18" /></svg>;
export const ImageIcon = ({ size = 18 }: P) => (
  <svg {...base(size)} strokeWidth={1.8}><rect x="3" y="4" width="18" height="16" rx="3" /><circle cx="9" cy="10" r="1.8" /><path d="M21 16l-5-5-9 9" /></svg>
);
