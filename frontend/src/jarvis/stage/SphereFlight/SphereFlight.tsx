import { SphereBurstLayer } from '@/jarvis/sphere/SphereBurstLayer/SphereBurstLayer';
import { useSpherePose } from '@/jarvis/stage/SphereFlight/useSpherePose';
import './SphereFlight.css';

export const SphereFlight = () => {
  const pose = useSpherePose();
  return (
    <div className="jarvis-sphere-flight" data-pose={pose} aria-hidden="true">
      <SphereBurstLayer />
    </div>
  );
};
