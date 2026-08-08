'use client';

import React, { useEffect, useRef, useState } from 'react';
import { AnimatePresence, type MotionProps, motion } from 'motion/react';
import {
  useAgent,
  useSessionContext,
  useSessionMessages,
} from '@livekit/components-react';

import { AgentChatTranscript } from '@/components/agents-ui/agent-chat-transcript';
import {
  AgentControlBar,
  type AgentControlBarControls,
} from '@/components/agents-ui/agent-control-bar';
import { Shimmer } from '@/components/ai-elements/shimmer';
import { cn } from '@/lib/shadcn/utils';

import { TileLayout } from './tile-view';

const MotionMessage = motion.create(Shimmer);

const BOTTOM_VIEW_MOTION_PROPS: MotionProps = {
  variants: {
    visible: {
      opacity: 1,
      translateY: '0%',
    },
    hidden: {
      opacity: 0,
      translateY: '100%',
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.3,
    delay: 0.5,
    ease: 'easeOut',
  },
};

const CHAT_MOTION_PROPS: MotionProps = {
  variants: {
    hidden: {
      opacity: 0,
      transition: {
        ease: 'easeOut',
        duration: 0.3,
      },
    },
    visible: {
      opacity: 1,
      transition: {
        delay: 0.2,
        ease: 'easeOut',
        duration: 0.3,
      },
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
};

const SHIMMER_MOTION_PROPS: MotionProps = {
  variants: {
    visible: {
      opacity: 1,
      transition: {
        ease: 'easeIn',
        duration: 0.5,
        delay: 0.8,
      },
    },
    hidden: {
      opacity: 0,
      transition: {
        ease: 'easeIn',
        duration: 0.5,
        delay: 0,
      },
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
};

interface FadeProps {
  top?: boolean;
  bottom?: boolean;
  className?: string;
}

export function Fade({
  top = false,
  bottom = false,
  className,
}: FadeProps) {
  return (
    <div
      className={cn(
        'from-background pointer-events-none h-4 bg-linear-to-b to-transparent',
        top && 'bg-linear-to-b',
        bottom && 'bg-linear-to-t',
        className
      )}
    />
  );
}

export interface AgentSessionView_01Props {
  preConnectMessage?: string;

  supportsChatInput?: boolean;

  supportsVideoInput?: boolean;

  supportsScreenShare?: boolean;

  isPreConnectBufferEnabled?: boolean;

  audioVisualizerType?: 'bar' | 'wave' | 'grid' | 'radial' | 'aura';

  audioVisualizerColor?: `#${string}`;

  audioVisualizerColorShift?: number;

  audioVisualizerBarCount?: number;

  audioVisualizerGridRowCount?: number;

  audioVisualizerGridColumnCount?: number;

  audioVisualizerRadialBarCount?: number;

  audioVisualizerRadialRadius?: number;

  audioVisualizerWaveLineWidth?: number;

  className?: string;

  onRestart?: () => void;
}

export function AgentSessionView_01({
  preConnectMessage = 'Agent is listening, ask it a question',

  supportsChatInput = true,

  supportsVideoInput = true,

  supportsScreenShare = true,

  isPreConnectBufferEnabled = true,

  audioVisualizerType,

  audioVisualizerColor,

  audioVisualizerColorShift,

  audioVisualizerBarCount,

  audioVisualizerGridRowCount,

  audioVisualizerGridColumnCount,

  audioVisualizerRadialBarCount,

  audioVisualizerRadialRadius,

  audioVisualizerWaveLineWidth,

  ref,

  className,

  onRestart,

  ...props
}: React.ComponentProps<'section'> & AgentSessionView_01Props) {
  const session = useSessionContext();

  const { messages } = useSessionMessages(session);

  const [chatOpen, setChatOpen] = useState(false);

  const scrollAreaRef = useRef<HTMLDivElement | null>(null);

  // IMPORTANT:
  // Declare agentState ONLY ONCE.
  const { state: agentState } = useAgent();

  /*
   * Convert LiveKit's internal state into text
   * that the user can understand.
   */
  const statusText: Record<string, string> = {
    connecting: 'Connecting to Suchi...',
    'pre-connect-buffering': 'Getting ready...',
    initializing: 'Starting your support session...',
    idle: 'Suchi is ready.',
    listening: 'Listening to you',
    thinking: 'Suchi is thinking...',
    speaking: 'Suchi is speaking',
    disconnected: 'Call ended',
    failed: 'Something went wrong',
  };

  const currentStatus =
    statusText[agentState] ?? 'Connecting...';

  /*
   * Determine whether the call has ended.
   */
  const isCallEnded =
    agentState === 'disconnected' ||
    agentState === 'failed';

  /*
   * Controls displayed at the bottom.
   */
  const controls: AgentControlBarControls = {
    leave: !isCallEnded,
    microphone: !isCallEnded,
    chat: !isCallEnded && supportsChatInput,
    camera: !isCallEnded && supportsVideoInput,
    screenShare: !isCallEnded && supportsScreenShare,
  };

  /*
   * Automatically scroll transcript when the user sends
   * a message.
   */
  useEffect(() => {
    const lastMessage = messages.at(-1);

    const lastMessageIsLocal =
      lastMessage?.from?.isLocal === true;

    if (
      scrollAreaRef.current &&
      lastMessageIsLocal
    ) {
      scrollAreaRef.current.scrollTop =
        scrollAreaRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <section
      ref={ref}
      className={cn(
        'bg-background relative z-10 h-full w-full overflow-hidden',
        className
      )}
      {...props}
    >
      {/* STATUS BAR */}

      <div className="pointer-events-none absolute left-0 right-0 top-5 z-50 flex justify-center">
        <div
          className={cn(
            'rounded-full px-5 py-2 text-sm font-medium shadow-sm',
            isCallEnded
              ? 'bg-muted text-muted-foreground'
              : 'bg-background/80 text-foreground backdrop-blur-md'
          )}
        >
          {currentStatus}
        </div>
      </div>

      {/* TRANSCRIPT */}

      <div className="absolute top-0 bottom-[135px] flex w-full flex-col md:bottom-[170px]">
        <AnimatePresence>
          {chatOpen && (
            <motion.div
              {...CHAT_MOTION_PROPS}
              className="flex h-full w-full flex-col gap-4 space-y-3 transition-opacity duration-300 ease-out"
            >
              <AgentChatTranscript
                agentState={agentState}
                messages={messages}
                className="mx-auto w-full max-w-2xl [&_.is-user>div]:rounded-[22px] [&>div>div]:px-4 [&>div>div]:pt-40 md:[&>div>div]:px-6"
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* AUDIO VISUALIZER */}

      <TileLayout
        chatOpen={chatOpen}
        audioVisualizerType={audioVisualizerType}
        audioVisualizerColor={audioVisualizerColor}
        audioVisualizerColorShift={audioVisualizerColorShift}
        audioVisualizerBarCount={audioVisualizerBarCount}
        audioVisualizerRadialBarCount={
          audioVisualizerRadialBarCount
        }
        audioVisualizerRadialRadius={
          audioVisualizerRadialRadius
        }
        audioVisualizerGridRowCount={
          audioVisualizerGridRowCount
        }
        audioVisualizerGridColumnCount={
          audioVisualizerGridColumnCount
        }
        audioVisualizerWaveLineWidth={
          audioVisualizerWaveLineWidth
        }
      />

      {/* BOTTOM CONTROLS */}

      <motion.div
        {...BOTTOM_VIEW_MOTION_PROPS}
        className="absolute inset-x-3 bottom-0 z-50 md:inset-x-12"
      >
        {/* STATUS MESSAGE */}

        {isPreConnectBufferEnabled && (
          <AnimatePresence>
            {messages.length === 0 && !isCallEnded && (
              <MotionMessage
                key="pre-connect-message"
                duration={2}
                aria-hidden={messages.length > 0}
                {...SHIMMER_MOTION_PROPS}
                className="pointer-events-none mx-auto block w-full max-w-2xl pb-4 text-center text-sm font-semibold"
              >
                {currentStatus}
              </MotionMessage>
            )}
          </AnimatePresence>
        )}

        {/* CONTROLS */}

        {!isCallEnded && (
          <div className="bg-background relative mx-auto max-w-2xl pb-3 md:pb-12">
            <Fade
              bottom
              className="absolute inset-x-0 top-0 h-4 -translate-y-full"
            />

            <AgentControlBar
              variant="livekit"
              controls={controls}
              isChatOpen={chatOpen}
              isConnected={session.isConnected}
              onDisconnect={session.end}
              onIsChatOpenChange={setChatOpen}
            />
          </div>
        )}

        {/* CALL ENDED */}

        {isCallEnded && (
          <div className="bg-background relative mx-auto flex max-w-2xl flex-col items-center gap-4 pb-8 pt-4">
            <p className="text-muted-foreground text-sm">
              Your conversation with Suchi has ended.
            </p>

            <button
              type="button"
              onClick={onRestart}
              className="rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
            >
              Start again
            </button>
          </div>
        )}
      </motion.div>
    </section>
  );
}
