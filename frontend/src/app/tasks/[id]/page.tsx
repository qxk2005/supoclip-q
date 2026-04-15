"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet";
import { useSession } from "@/lib/auth-client";
import { formatSupportMessage, parseApiError } from "@/lib/api-error";
import {
  ArrowLeft,
  Download,
  Star,
  AlertCircle,
  Trash2,
  Edit2,
  X,
  Check,
  Zap,
  MessageSquare,
  TrendingUp,
  Share2,
  Clock,
  Scissors,
  SplitSquareVertical,
  GitMerge,
  RefreshCw,
  Subtitles,
  Settings2,
  Type,
  Clapperboard,
} from "lucide-react";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { Progress } from "@/components/ui/progress";
import Link from "next/link";
import DynamicVideoPlayer from "@/components/dynamic-video-player";

interface Clip {
  id: string;
  filename: string;
  file_path: string;
  start_time: string;
  end_time: string;
  duration: number;
  text: string;
  text_translation?: string | null;
  relevance_score: number;
  reasoning: string;
  clip_order: number;
  created_at: string;
  video_url: string;
  // Virality scores
  virality_score: number;
  hook_score: number;
  engagement_score: number;
  value_score: number;
  shareability_score: number;
  hook_type: string | null;
}

interface TaskDetails {
  id: string;
  user_id: string;
  source_id: string;
  source_title: string;
  source_type: string;
  status: string;
  progress?: number;
  progress_message?: string;
  clips_count: number;
  created_at: string;
  updated_at: string;
  font_family?: string;
  font_size?: number;
  font_color?: string;
  caption_template?: string;
  include_broll?: boolean;
}

interface FontOption {
  name: string;
  display_name: string;
}

export default function TaskPage() {
  const params = useParams();
  const router = useRouter();
  const { data: session } = useSession();
  const [task, setTask] = useState<TaskDetails | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [editedTitle, setEditedTitle] = useState("");
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deletingClipId, setDeletingClipId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectedClipIds, setSelectedClipIds] = useState<string[]>([]);
  const [editingClipId, setEditingClipId] = useState<string | null>(null);
  const [startOffset, setStartOffset] = useState("0");
  const [endOffset, setEndOffset] = useState("0");
  const [splitTime, setSplitTime] = useState("5");
  const [captionText, setCaptionText] = useState("");
  const [captionPosition, setCaptionPosition] = useState("bottom");
  const [highlightWords, setHighlightWords] = useState("");
  const [exportPreset, setExportPreset] = useState("tiktok");

  const [projectFontFamily, setProjectFontFamily] = useState("TikTokSans-Regular");
  const [projectFontSize, setProjectFontSize] = useState("24");
  const [projectFontColor, setProjectFontColor] = useState("#FFFFFF");
  const [projectCaptionTemplate, setProjectCaptionTemplate] = useState("default");
  const [projectIncludeBroll, setProjectIncludeBroll] = useState(false);
  const [projectAudioFadeIn, setProjectAudioFadeIn] = useState(false);
  const [projectAudioFadeOut, setProjectAudioFadeOut] = useState(false);
  const [projectProcessingMode, setProjectProcessingMode] = useState<'fast' | 'balanced' | 'quality'>('fast');
  const [isApplyingSettings, setIsApplyingSettings] = useState(false);
  const [settingsSheetOpen, setSettingsSheetOpen] = useState(false);
  const [availableFonts, setAvailableFonts] = useState<FontOption[]>([]);
  const [availableTemplates, setAvailableTemplates] = useState<
    Array<{ id: string; name: string; description: string; animation: string }>
  >([]);
  const hasTriggeredAutoRefresh = useRef(false);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const taskApiUrl = "/api/tasks";

  const buildSupportError = useCallback(async (response: Response, fallbackMessage: string) => {
    const parsed = await parseApiError(response, fallbackMessage);
    return formatSupportMessage(parsed);
  }, []);

  const triggerAutoRefresh = useCallback(() => {
    if (hasTriggeredAutoRefresh.current) return;
    hasTriggeredAutoRefresh.current = true;
    setTimeout(() => {
      window.location.reload();
    }, 700);
  }, []);

  const fetchTaskStatus = useCallback(
    async (retryCount = 0, maxRetries = 5) => {
      if (!params.id) return false;

      try {
        const taskResponse = await fetch(`${taskApiUrl}/${params.id}`, {
          cache: "no-store",
        });

        // Handle 404 with retry logic (task might not be persisted yet)
        if (taskResponse.status === 404 && retryCount < maxRetries) {
          console.log(
            `Task not found yet, retrying in ${(retryCount + 1) * 500}ms... (${retryCount + 1}/${maxRetries})`,
          );
          await new Promise((resolve) => setTimeout(resolve, (retryCount + 1) * 500));
          return fetchTaskStatus(retryCount + 1, maxRetries);
        }

        if (!taskResponse.ok) {
          throw new Error(await buildSupportError(taskResponse, `获取任务失败：${taskResponse.status}`));
        }

        const taskData = await taskResponse.json();
        setTask(taskData);
        setProjectFontFamily(taskData.font_family || "TikTokSans-Regular");
        setProjectFontSize(String(taskData.font_size || 24));
        setProjectFontColor(taskData.font_color || "#FFFFFF");
        setProjectCaptionTemplate(taskData.caption_template || "default");
        setProjectIncludeBroll(Boolean(taskData.include_broll));
        setProjectAudioFadeIn(Boolean(taskData.audio_fade_in));
        setProjectAudioFadeOut(Boolean(taskData.audio_fade_out));
        setProjectProcessingMode(taskData.processing_mode || "fast");

        // Fetch clips if task is completed or processing (incremental clips)
        if (taskData.status === "completed" || taskData.status === "processing") {
          const clipsResponse = await fetch(`${taskApiUrl}/${params.id}/clips`, {
            cache: "no-store",
          });

          if (!clipsResponse.ok) {
            throw new Error(await buildSupportError(clipsResponse, `获取片段失败：${clipsResponse.status}`));
          }

          const clipsData = await clipsResponse.json();
          const nextClips = clipsData.clips || [];
          setClips((prev) => {
            if (taskData.status === "completed") {
              return nextClips;
            }

            const merged = new Map<string, Clip>();
            for (const clip of prev) {
              merged.set(clip.id, clip);
            }
            for (const clip of nextClips) {
              merged.set(clip.id, clip);
            }
            return Array.from(merged.values()).sort(
              (a, b) => (a.clip_order ?? 0) - (b.clip_order ?? 0),
            );
          });
        }

        return true;
      } catch (err) {
        console.error("Error fetching task data:", err);
        setError(err instanceof Error ? err.message : "加载任务失败");
        return false;
      }
    },
    [buildSupportError, params.id, taskApiUrl],
  );

  // Initial fetch - runs immediately, doesn't wait for session
  useEffect(() => {
    if (!params.id) return;

    const fetchTaskData = async () => {
      try {
        setIsLoading(true);
        await fetchTaskStatus();
      } finally {
        setIsLoading(false);
      }
    };

    fetchTaskData();
  }, [params.id, fetchTaskStatus]);

  useEffect(() => {
    const loadFonts = async () => {
      try {
        const response = await fetch("/api/fonts", { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        setAvailableFonts(data.fonts || []);
      } catch (loadError) {
        console.error("Failed to load fonts:", loadError);
      }
    };

    void loadFonts();

    const loadTemplates = async () => {
      try {
        const response = await fetch(`${apiUrl}/caption-templates`);
        if (response.ok) {
          const data = await response.json();
          setAvailableTemplates(data.templates || []);
        }
      } catch (error) {
        console.error("Failed to load caption templates:", error);
      }
    };
    void loadTemplates();
  }, [apiUrl]);

  // SSE effect - real-time progress updates
  useEffect(() => {
    const taskStatus = task?.status;
    if (!params.id || !taskStatus) return;

    // Only connect to SSE if task is queued or processing
    if (taskStatus !== "queued" && taskStatus !== "processing") return;

    /** Set when the stream ends normally (server `close` or React cleanup) — browser still fires `error` on EOF. */
    let expectDisconnect = false;

    const eventSource = new EventSource(`${taskApiUrl}/${params.id}/progress`);

    console.log("📡 Connected to SSE for real-time progress");

    eventSource.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      console.log("📊 Status:", data);
      setProgress(data.progress || 0);
      setProgressMessage(data.message || "");

      if (data.status === "completed") {
        void fetchTaskStatus().then(() => triggerAutoRefresh());
      }
    });

    eventSource.addEventListener("progress", (e) => {
      const data = JSON.parse(e.data);
      console.log("📈 Progress:", data);
      setProgress(data.progress || 0);
      setProgressMessage(data.message || "");

      // Update task status if provided
      if (data.status) {
        setTask((currentTask) => (currentTask ? { ...currentTask, status: data.status } : currentTask));

        if (data.status === "completed") {
          void fetchTaskStatus().then(() => triggerAutoRefresh());
        }
      }
    });

    eventSource.addEventListener("clip_ready", (e) => {
      const data = JSON.parse(e.data);
      console.log("🎬 Clip ready:", data.clip_index + 1, "/", data.total_clips);
      if (data.clip) {
        setClips((prev) => {
          const exists = prev.some((c: Clip) => c.id === data.clip.id);
          if (exists) return prev;
          return [...prev, data.clip].sort(
            (a: Clip, b: Clip) => (a.clip_order ?? 0) - (b.clip_order ?? 0),
          );
        });
      }
    });

    eventSource.addEventListener("close", async (e) => {
      expectDisconnect = true;
      const data = JSON.parse(e.data);
      console.log("✅ Task completed:", data.status);
      eventSource.close();

      // Refresh task and clips
      await fetchTaskStatus();
      triggerAutoRefresh();
    });

    eventSource.addEventListener("error", () => {
      if (expectDisconnect) {
        return;
      }
      expectDisconnect = true;
      // EventSource `error` passes a generic Event (logs as `{}`); use readyState instead.
      const rs = eventSource.readyState;
      const stateName =
        rs === EventSource.CONNECTING ? "CONNECTING" : rs === EventSource.OPEN ? "OPEN" : "CLOSED";
      console.warn("SSE connection lost:", { readyState: rs, stateName, url: eventSource.url });
      eventSource.close();
    });

    return () => {
      expectDisconnect = true;
      console.log("🔌 Disconnecting SSE");
      eventSource.close();
    };
  }, [params.id, task?.status, fetchTaskStatus, taskApiUrl, triggerAutoRefresh]); // Re-run when task status changes

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return "bg-green-100 text-green-800";
    if (score >= 0.6) return "bg-yellow-100 text-yellow-800";
    return "bg-red-100 text-red-800";
  };

  const getViralityColor = (score: number) => {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    if (score >= 40) return "text-orange-600";
    return "text-red-600";
  };

  const getViralityBgColor = (score: number) => {
    if (score >= 80) return "bg-green-500";
    if (score >= 60) return "bg-yellow-500";
    if (score >= 40) return "bg-orange-500";
    return "bg-red-500";
  };

  const getHookTypeLabel = (hookType: string | null) => {
    const labels: Record<string, string> = {
      question: "提问式钩子",
      statement: "观点式钩子",
      statistic: "数据/统计",
      story: "故事式钩子",
      contrast: "对比式钩子",
      none: "无特定钩子",
    };
    return labels[hookType || "none"] || hookType || "无";
  };

  const handleEditTitle = async () => {
    if (!editedTitle.trim() || !session?.user?.id || !params.id) return;

    try {
      const response = await fetch(`${taskApiUrl}/${params.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ title: editedTitle }),
      });

      if (response.ok) {
        setTask(task ? { ...task, source_title: editedTitle } : null);
        setIsEditing(false);
      } else {
        alert(await buildSupportError(response, "更新标题失败"));
      }
    } catch (err) {
      console.error("Error updating title:", err);
      alert(err instanceof Error ? err.message : "更新标题失败");
    }
  };

  const handleDeleteTask = async () => {
    if (!session?.user?.id || !params.id) return;

    setIsDeleting(true);
    try {
      const response = await fetch(`${taskApiUrl}/${params.id}`, {
        method: "DELETE",
      });

      if (response.ok) {
        router.push("/list");
      } else {
        alert(await buildSupportError(response, "删除任务失败"));
      }
    } catch (err) {
      console.error("Error deleting task:", err);
      alert(err instanceof Error ? err.message : "删除任务失败");
    } finally {
      setIsDeleting(false);
      setShowDeleteDialog(false);
    }
  };

  const handleDeleteClip = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;

    try {
      const response = await fetch(`${taskApiUrl}/${params.id}/clips/${clipId}`, {
        method: "DELETE",
      });

      if (response.ok) {
        setClips(clips.filter((clip) => clip.id !== clipId));
        setDeletingClipId(null);
      } else {
        alert(await buildSupportError(response, "删除片段失败"));
      }
    } catch (err) {
      console.error("Error deleting clip:", err);
      alert(err instanceof Error ? err.message : "删除片段失败");
    }
  };

  const handleToggleClipSelection = (clipId: string) => {
    setSelectedClipIds((prev) => {
      if (prev.includes(clipId)) {
        return prev.filter((id) => id !== clipId);
      }
      return [...prev, clipId];
    });
  };

  const handleTrimClip = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;
    const response = await fetch(`${taskApiUrl}/${params.id}/clips/${clipId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        start_offset: Number(startOffset || "0"),
        end_offset: Number(endOffset || "0"),
      }),
    });
    if (!response.ok) {
      alert(await buildSupportError(response, "裁剪片段失败"));
      return;
    }
    await fetchTaskStatus();
  };

  const handleSplitClip = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;
    const response = await fetch(`${taskApiUrl}/${params.id}/clips/${clipId}/split`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ split_time: Number(splitTime || "5") }),
    });
    if (!response.ok) {
      alert(await buildSupportError(response, "分割片段失败"));
      return;
    }
    await fetchTaskStatus();
  };

  const handleMergeClips = async () => {
    if (!session?.user?.id || !params.id || selectedClipIds.length < 2) return;
    const response = await fetch(`${taskApiUrl}/${params.id}/clips/merge`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ clip_ids: selectedClipIds }),
    });
    if (!response.ok) {
      alert(await buildSupportError(response, "合并片段失败"));
      return;
    }
    setSelectedClipIds([]);
    await fetchTaskStatus();
  };

  const handleUpdateCaptions = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;
    const response = await fetch(`${taskApiUrl}/${params.id}/clips/${clipId}/captions`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        caption_text: captionText,
        position: captionPosition,
        highlight_words: highlightWords
          .split(",")
          .map((w) => w.trim())
          .filter(Boolean),
      }),
    });
    if (!response.ok) {
      alert(await buildSupportError(response, "更新字幕失败"));
      return;
    }
    await fetchTaskStatus();
  };

  const handleApplyProjectSettings = async () => {
    if (!session?.user?.id || !params.id) return;
    const parsedSize = Number(projectFontSize || "24");
    const safeFontSize = Number.isFinite(parsedSize) ? Math.max(12, Math.min(72, Math.round(parsedSize))) : 24;
    const normalizedColor = /^#[0-9A-Fa-f]{6}$/.test(projectFontColor) ? projectFontColor : "#FFFFFF";

    setIsApplyingSettings(true);
    try {
      const response = await fetch(`${taskApiUrl}/${params.id}/settings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          font_family: projectFontFamily,
          font_size: safeFontSize,
          font_color: normalizedColor,
          caption_template: projectCaptionTemplate,
          include_broll: projectIncludeBroll,
          audio_fade_in: projectAudioFadeIn,
          audio_fade_out: projectAudioFadeOut,
          processing_mode: projectProcessingMode,
          apply_to_existing: task?.status === "completed",
        }),
      });
      if (!response.ok) {
        alert(await buildSupportError(response, "应用设置失败"));
        return;
      }
      await fetchTaskStatus();
    } finally {
      setIsApplyingSettings(false);
    }
  };

  const handleExportClip = async (clipId: string, fallbackFilename: string) => {
    if (!session?.user?.id || !task?.id) return;

    const response = await fetch(`${taskApiUrl}/${task.id}/clips/${clipId}/export?preset=${exportPreset}`, {
      cache: "no-store",
    });

    if (!response.ok) {
      alert(await buildSupportError(response, "导出片段失败"));
      return;
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = `${fallbackFilename.replace(/\.mp4$/i, "")}_${exportPreset}.mp4`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white p-4">
        <div className="max-w-6xl mx-auto">
          <div className="mb-6">
            <Skeleton className="h-8 w-48 mb-2" />
            <Skeleton className="h-4 w-96" />
          </div>
          <div className="grid gap-6">
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardContent className="p-6">
                  <Skeleton className="h-48 w-full mb-4" />
                  <Skeleton className="h-4 w-full mb-2" />
                  <Skeleton className="h-4 w-3/4" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-white p-4">
        <div className="max-w-6xl mx-auto">
          <Alert>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <Link href="/" className="mt-4 inline-block">
            <Button variant="outline">
              <ArrowLeft className="w-4 h-4" />
              返回首页
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="border-b bg-white">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <div className="flex items-center gap-4 mb-4">
            <Link href="/">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="w-4 h-4" />
                返回
              </Button>
            </Link>
          </div>

          {task && (
            <div>
              <div className="flex items-center gap-3 mb-2">
                {isEditing ? (
                  <div className="flex items-center gap-2 flex-1">
                    <Input
                      value={editedTitle}
                      onChange={(e) => setEditedTitle(e.target.value)}
                      className="text-2xl font-bold h-auto py-1"
                      autoFocus
                    />
                    <Button size="sm" onClick={handleEditTitle} disabled={!editedTitle.trim()}>
                      <Check className="w-4 h-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setIsEditing(false);
                        setEditedTitle(task.source_title);
                      }}
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                ) : (
                  <>
                    <h1 className={`text-2xl font-bold text-black ${task.status === "processing" || task.status === "queued" ? "shimmer" : ""}`}>{task.source_title}</h1>
                    <div className="flex items-center gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setIsEditing(true);
                          setEditedTitle(task.source_title);
                        }}
                      >
                        <Edit2 className="w-4 h-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        onClick={() => setShowDeleteDialog(true)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </>
                )}
              </div>
              <div className="flex items-center gap-4 text-sm text-gray-600">
                <Badge variant="outline" className="capitalize">
                  {task.source_type}
                </Badge>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="flex items-center gap-1 cursor-default">
                        <Clock className="w-4 h-4" />
                        {new Date(task.created_at).toLocaleDateString("zh-CN", { year: "numeric", month: "short", day: "numeric" })}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      {new Date(task.created_at).toLocaleString("zh-CN", {
                        year: "numeric",
                        month: "long",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                        timeZoneName: "short",
                      })}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                {task.status === "completed" ? (
                  <span>
                    已生成 {clips.length} 个片段
                  </span>
                ) : task.status === "processing" ? (
                  <div className="relative group">
                    <Badge className="bg-blue-100 text-blue-800 cursor-default shimmer">处理中</Badge>
                    <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md opacity-0 scale-95 transition-all group-hover:opacity-100 group-hover:scale-100 pointer-events-none">
                      🔍&nbsp;&nbsp;正在处理视频，请几分钟后再来看。
                    </div>
                  </div>
                ) : task.status === "queued" ? (
                  <Badge className="bg-yellow-100 text-yellow-800">排队中</Badge>
                ) : (
                  <Badge variant="outline" className="capitalize">
                    {task.status}
                  </Badge>
                )}
                {task.status === "completed" && clips.length > 0 && (
                  <Link href={`/tasks/${task.id}/edit`}>
                    <Button size="sm" variant="outline">
                      <Clapperboard className="w-4 h-4" />
                      打开编辑器
                    </Button>
                  </Link>
                )}
                {(task.status === "queued" || task.status === "processing") && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setSettingsSheetOpen(true)}
                    >
                      <Settings2 className="w-4 h-4" />
                      项目设置
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={async () => {
                        await fetch(`${taskApiUrl}/${task.id}/cancel`, {
                          method: "POST",
                        });
                        await fetchTaskStatus();
                      }}
                    >
                      取消
                    </Button>
                  </>
                )}
                {(task.status === "cancelled" || task.status === "error") && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={async () => {
                      await fetch(`${taskApiUrl}/${task.id}/resume`, {
                        method: "POST",
                      });
                      await fetchTaskStatus();
                    }}
                  >
                    恢复
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto px-4 py-8">
        {task?.status === "processing" || task?.status === "queued" ? (
          <div className="space-y-8">
            {/* Progress indicator */}
            <div className="flex flex-col items-center py-8">
              {/* Minimal animated dots */}
              <div className="relative group flex items-center gap-1.5 mb-8 cursor-default">
                <span className="w-2 h-2 bg-neutral-800 rounded-full animate-[pulse_1.4s_ease-in-out_infinite]" />
                <span className="w-2 h-2 bg-neutral-800 rounded-full animate-[pulse_1.4s_ease-in-out_0.2s_infinite]" />
                <span className="w-2 h-2 bg-neutral-800 rounded-full animate-[pulse_1.4s_ease-in-out_0.4s_infinite]" />
                <div className="absolute top-full mt-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md opacity-0 scale-95 transition-all group-hover:opacity-100 group-hover:scale-100 pointer-events-none">
                  ☕&nbsp;&nbsp;喝杯咖啡，回来即可下载成片。
                </div>
              </div>

              {/* Status message */}
              <p className="shimmer text-neutral-600/60 text-sm tracking-wide mb-8">
                {progressMessage || (task.status === "queued" ? "排队等待中" : "处理中")}
              </p>

              {/* Minimal progress bar */}
              {progress > 0 && (
                <div className="w-48">
                  <div className="h-px bg-neutral-200 w-full relative overflow-hidden">
                    <div
                      className="absolute inset-y-0 left-0 bg-neutral-800 transition-all duration-700 ease-out"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-neutral-400 text-center mt-3 tabular-nums">{progress}%</p>
                </div>
              )}
            </div>

            {/* Live clips grid — shows clips as they render */}
            {clips.length > 0 && (
              <div className="grid gap-6">
                <p className="text-sm text-neutral-500 text-center">
                  已有 {clips.length} 个片段就绪
                </p>
                {clips.map((clip) => (
                  <Card key={clip.id} className="overflow-hidden">
                    <CardContent className="p-0">
                      <div className="flex flex-col lg:flex-row">
                        <div className="relative flex-shrink-0 bg-black rounded-lg overflow-hidden m-3">
                          <DynamicVideoPlayer src={`${apiUrl}${clip.video_url}`} poster="/placeholder-video.jpg" />
                        </div>
                        <div className="p-6 flex-1">
                          <div className="flex items-start justify-between mb-4">
                            <div>
                              <h3 className="font-semibold text-lg text-black mb-1">片段 {clip.clip_order}</h3>
                              <div className="flex items-center gap-2 text-sm text-gray-600">
                                <span>{clip.start_time} - {clip.end_time}</span>
                                <span>•</span>
                                <span>{formatDuration(clip.duration)}</span>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {clip.virality_score > 0 && (
                                <Badge className={`${getViralityBgColor(clip.virality_score)} text-white`}>
                                  <Zap className="w-3 h-3 mr-1" />
                                  {clip.virality_score}
                                </Badge>
                              )}
                              <Badge className={getScoreColor(clip.relevance_score)}>
                                <Star className="w-3 h-3 mr-1" />
                                {(clip.relevance_score * 100).toFixed(0)}%
                              </Badge>
                            </div>
                          </div>
                          {clip.text && (
                            <div className="mb-4">
                              <h4 className="font-medium text-black mb-2">转写文本</h4>
                              <p className="text-sm text-gray-700 bg-gray-50 p-3 rounded">{clip.text}</p>
                              {clip.text_translation ? (
                                <div className="mt-2">
                                  <h5 className="text-xs font-medium text-gray-500 mb-1">中文译文</h5>
                                  <p className="text-sm text-gray-700 bg-stone-50 p-3 rounded border border-stone-100">
                                    {clip.text_translation}
                                  </p>
                                </div>
                              ) : null}
                            </div>
                          )}
                          {clip.reasoning && (
                            <div className="mb-4">
                              <h4 className="font-medium text-black mb-2">AI 分析</h4>
                              <p className="text-sm text-gray-600 whitespace-pre-wrap">{clip.reasoning}</p>
                            </div>
                          )}
                          <Button size="sm" variant="outline" asChild>
                            <a href={`${apiUrl}${clip.video_url}`} download={clip.filename}>
                              <Download className="w-4 h-4" />
                              下载
                            </a>
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        ) : !task ? (
          <div className="flex flex-col items-center justify-center min-h-[50vh] py-16">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 bg-neutral-300 rounded-full animate-[pulse_1.4s_ease-in-out_infinite]" />
              <span className="w-2 h-2 bg-neutral-300 rounded-full animate-[pulse_1.4s_ease-in-out_0.2s_infinite]" />
              <span className="w-2 h-2 bg-neutral-300 rounded-full animate-[pulse_1.4s_ease-in-out_0.4s_infinite]" />
            </div>
          </div>
        ) : task?.status === "error" ? (
          <Card>
            <CardContent className="p-8 text-center">
              <div className="text-red-600 mb-4">
                <AlertCircle className="w-12 h-12 mx-auto mb-2" />
                <h2 className="text-xl font-semibold">处理失败</h2>
              </div>
              <p className="text-gray-600 mb-4 whitespace-pre-wrap">
                {task.progress_message || error || "处理视频时出错，请重试。"}
              </p>
              <Link href="/">
                <Button>
                  <ArrowLeft className="w-4 h-4" />
                  返回首页
                </Button>
              </Link>
            </CardContent>
          </Card>
        ) : clips.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center">
              {task?.status === "completed" ? (
                <>
                  <div className="text-yellow-600 mb-4">
                    <AlertCircle className="w-12 h-12 mx-auto mb-2" />
                    <h2 className="text-xl font-semibold">未生成片段</h2>
                  </div>
                  <p className="text-gray-600 mb-4">
                    任务已完成，但没有生成片段。可能是视频内容不适合剪片。
                  </p>
                  <Link href="/">
                    <Button>
                      <ArrowLeft className="w-4 h-4" />
                      换一条视频试试
                    </Button>
                  </Link>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Clock className="w-8 h-8 text-blue-500 animate-pulse" />
                  </div>
                  <h2 className="text-xl font-semibold text-black mb-2">仍在生成中…</h2>
                  <p className="text-gray-600">
                    片段生成完成后，本页面会自动刷新。
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-6">
            <div className="flex items-center justify-between">
              <Button variant="outline" size="sm" onClick={() => setSettingsSheetOpen(true)}>
                <Settings2 className="w-4 h-4" />
                项目设置
              </Button>
              {selectedClipIds.length >= 2 && (
                <Button variant="outline" size="sm" onClick={handleMergeClips}>
                  <GitMerge className="w-4 h-4" />
                  合并所选（{selectedClipIds.length}）
                </Button>
              )}
            </div>

            {clips.map((clip) => (
              <Card key={clip.id} className="overflow-hidden">
                <CardContent className="p-0">
                  <div className="flex flex-col lg:flex-row">
                    {/* Video Player */}
                    <div className="relative flex-shrink-0 bg-black rounded-lg overflow-hidden m-3">
                      <DynamicVideoPlayer src={`${apiUrl}${clip.video_url}`} poster="/placeholder-video.jpg" />
                    </div>

                    {/* Clip Details */}
                    <div className="p-6 flex-1">
                      <div className="flex items-start justify-between mb-4">
                        <div>
                          <label className="flex items-center gap-2 text-xs text-gray-600 mb-2">
                            <input
                              type="checkbox"
                              checked={selectedClipIds.includes(clip.id)}
                              onChange={() => handleToggleClipSelection(clip.id)}
                            />
                            加入合并
                          </label>
                          <h3 className="font-semibold text-lg text-black mb-1">片段 {clip.clip_order}</h3>
                          <div className="flex items-center gap-2 text-sm text-gray-600">
                            <span>
                              {clip.start_time} - {clip.end_time}
                            </span>
                            <span>•</span>
                            <span>{formatDuration(clip.duration)}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {/* Virality Score Badge */}
                          {clip.virality_score > 0 && (
                            <Badge className={`${getViralityBgColor(clip.virality_score)} text-white`}>
                              <Zap className="w-3 h-3 mr-1" />
                              {clip.virality_score}
                            </Badge>
                          )}
                          <Badge className={getScoreColor(clip.relevance_score)}>
                            <Star className="w-3 h-3 mr-1" />
                            {(clip.relevance_score * 100).toFixed(0)}%
                          </Badge>
                        </div>
                      </div>

                      {/* Virality Score Breakdown */}
                      {clip.virality_score > 0 && (
                        <div className="mb-4 p-3 bg-gray-50 rounded-lg">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="font-medium text-black text-sm flex items-center gap-2">
                              <Zap className="w-4 h-4" />
                              传播力得分
                            </h4>
                            <span className={`text-lg font-bold ${getViralityColor(clip.virality_score)}`}>
                              {clip.virality_score}/100
                            </span>
                          </div>

                          <div className="grid grid-cols-2 gap-3 text-xs">
                            {/* Hook Score */}
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="flex items-center gap-1 text-gray-600">
                                  <MessageSquare className="w-3 h-3" />
                                  钩子
                                </span>
                                <span className="font-medium">{clip.hook_score}/25</span>
                              </div>
                              <Progress value={(clip.hook_score / 25) * 100} className="h-1.5" />
                            </div>

                            {/* Engagement Score */}
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="flex items-center gap-1 text-gray-600">
                                  <TrendingUp className="w-3 h-3" />
                                  互动
                                </span>
                                <span className="font-medium">{clip.engagement_score}/25</span>
                              </div>
                              <Progress value={(clip.engagement_score / 25) * 100} className="h-1.5" />
                            </div>

                            {/* Value Score */}
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="flex items-center gap-1 text-gray-600">
                                  <Star className="w-3 h-3" />
                                  价值
                                </span>
                                <span className="font-medium">{clip.value_score}/25</span>
                              </div>
                              <Progress value={(clip.value_score / 25) * 100} className="h-1.5" />
                            </div>

                            {/* Shareability Score */}
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="flex items-center gap-1 text-gray-600">
                                  <Share2 className="w-3 h-3" />
                                  分享性
                                </span>
                                <span className="font-medium">{clip.shareability_score}/25</span>
                              </div>
                              <Progress value={(clip.shareability_score / 25) * 100} className="h-1.5" />
                            </div>
                          </div>

                          {clip.hook_type && clip.hook_type !== "none" && (
                            <div className="mt-3 pt-2 border-t">
                              <Badge variant="outline" className="text-xs">
                                {getHookTypeLabel(clip.hook_type)}
                              </Badge>
                            </div>
                          )}
                        </div>
                      )}

                      {clip.text && (
                        <div className="mb-4">
                          <h4 className="font-medium text-black mb-2">转写文本</h4>
                          <p className="text-sm text-gray-700 bg-gray-50 p-3 rounded">{clip.text}</p>
                          {clip.text_translation ? (
                            <div className="mt-2">
                              <h5 className="text-xs font-medium text-gray-500 mb-1">中文译文</h5>
                              <p className="text-sm text-gray-700 bg-stone-50 p-3 rounded border border-stone-100">
                                {clip.text_translation}
                              </p>
                            </div>
                          ) : null}
                        </div>
                      )}

                      {clip.reasoning && (
                        <div className="mb-4">
                          <h4 className="font-medium text-black mb-2">AI 分析</h4>
                          <p className="text-sm text-gray-600 whitespace-pre-wrap">{clip.reasoning}</p>
                        </div>
                      )}

                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" asChild>
                          <a href={`${apiUrl}${clip.video_url}`} download={clip.filename}>
                            <Download className="w-4 h-4" />
                            下载
                          </a>
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => handleExportClip(clip.id, clip.filename)}>
                          <Download className="w-4 h-4" />
                          导出
                        </Button>
                        <Select value={exportPreset} onValueChange={setExportPreset}>
                          <SelectTrigger className="h-8 w-28">
                            <SelectValue placeholder="预设" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="tiktok">TikTok</SelectItem>
                            <SelectItem value="reels">Reels</SelectItem>
                            <SelectItem value="shorts">Shorts</SelectItem>
                          </SelectContent>
                        </Select>
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                          onClick={() => setDeletingClipId(clip.id)}
                        >
                          <Trash2 className="w-4 h-4" />
                          删除
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditingClipId(editingClipId === clip.id ? null : clip.id);
                            setCaptionText(clip.text || "");
                          }}
                        >
                          <Scissors className="w-4 h-4" />
                          编辑
                        </Button>
                      </div>

                      {editingClipId === clip.id && (
                        <div className="mt-4 p-3 border rounded-lg space-y-3 bg-gray-50">
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                            <Input
                              value={startOffset}
                              onChange={(e) => setStartOffset(e.target.value)}
                              placeholder="起点裁剪（秒）"
                            />
                            <Input
                              value={endOffset}
                              onChange={(e) => setEndOffset(e.target.value)}
                              placeholder="终点裁剪（秒）"
                            />
                            <Button size="sm" onClick={() => handleTrimClip(clip.id)}>
                              <Scissors className="w-4 h-4" />
                              裁剪
                            </Button>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                            <Input
                              value={splitTime}
                              onChange={(e) => setSplitTime(e.target.value)}
                              placeholder="在此秒数分割"
                            />
                            <Button size="sm" variant="outline" onClick={() => handleSplitClip(clip.id)}>
                              <SplitSquareVertical className="w-4 h-4" />
                              分割
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => handleTrimClip(clip.id)}>
                              <RefreshCw className="w-4 h-4" />
                              重新生成
                            </Button>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                            <Input
                              value={captionText}
                              onChange={(e) => setCaptionText(e.target.value)}
                              placeholder="字幕文案"
                            />
                            <Select value={captionPosition} onValueChange={setCaptionPosition}>
                              <SelectTrigger>
                                <SelectValue placeholder="字幕位置" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="top">顶部</SelectItem>
                                <SelectItem value="middle">中部</SelectItem>
                                <SelectItem value="bottom">底部</SelectItem>
                              </SelectContent>
                            </Select>
                            <Input
                              value={highlightWords}
                              onChange={(e) => setHighlightWords(e.target.value)}
                              placeholder="高亮词：词1, 词2"
                            />
                          </div>
                          <Button size="sm" variant="outline" onClick={() => handleUpdateCaptions(clip.id)}>
                            <Subtitles className="w-4 h-4" />
                            更新字幕
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {task && (
        <Sheet open={settingsSheetOpen} onOpenChange={setSettingsSheetOpen}>
          <SheetContent side="right" className="sm:max-w-md overflow-y-auto">
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <Settings2 className="w-4 h-4" />
                项目设置
              </SheetTitle>
              <SheetDescription>
                配置本任务的字体、字幕与音频。排队或处理中时保存会写入任务；生成片段时尚未输出的部分将使用最新设置。
                {task.status === "completed"
                  ? " 完成后可勾选「应用到全部片段」以按新设置重新渲染所有成片。"
                  : ""}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-5 px-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-500">字体</label>
                <Select value={projectFontFamily} onValueChange={setProjectFontFamily}>
                  <SelectTrigger>
                    <SelectValue placeholder="字体族" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableFonts.map((font) => (
                      <SelectItem key={font.name} value={font.name}>
                        <span className="flex items-center gap-2">
                          <Type className="w-3 h-3" />
                          {font.display_name}
                        </span>
                      </SelectItem>
                    ))}
                    {availableFonts.length === 0 && (
                      <SelectItem value="TikTokSans-Regular">TikTok Sans Regular</SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-500">字号</label>
                <Input
                  type="number"
                  min={12}
                  max={72}
                  value={projectFontSize}
                  onChange={(e) => setProjectFontSize(e.target.value)}
                  placeholder="字号"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-500">颜色</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={projectFontColor}
                    onChange={(e) => setProjectFontColor(e.target.value)}
                    className="h-9 w-9 rounded border border-gray-300 cursor-pointer"
                  />
                  <Input
                    value={projectFontColor}
                    onChange={(e) => setProjectFontColor(e.target.value)}
                    placeholder="#FFFFFF"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-500">字幕样式</label>
                <Select value={projectCaptionTemplate} onValueChange={setProjectCaptionTemplate}>
                  <SelectTrigger>
                    <SelectValue>
                      {projectCaptionTemplate === "bilingual"
                        ? "中英双语"
                        : availableTemplates.find((t) => t.id === projectCaptionTemplate)?.name || "选择样式"}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bilingual">
                      <div>
                        <div className="font-medium">中英双语</div>
                        <div className="text-xs text-gray-500">同时显示中文与英文字幕。</div>
                      </div>
                    </SelectItem>
                    {availableTemplates.map((template) => (
                      <SelectItem key={template.id} value={template.id}>
                        <div>
                          <div className="font-medium">{template.name}</div>
                          <div className="text-xs text-gray-500">{template.description}</div>
                        </div>
                      </SelectItem>
                    ))}
                    {availableTemplates.length === 0 && <SelectItem value="default">默认</SelectItem>}
                  </SelectContent>
                </Select>
              </div>

              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={projectIncludeBroll}
                  onChange={(e) => setProjectIncludeBroll(e.target.checked)}
                  className="rounded"
                />
                包含 B-Roll
              </label>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-500">处理模式</label>
                <Select
                  value={projectProcessingMode}
                  onValueChange={(value) => setProjectProcessingMode(value as "fast" | "balanced" | "quality")}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择处理模式" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fast">
                      <div>
                        <div className="font-medium">快速</div>
                        <div className="text-xs text-gray-500">优先速度，生成少量高相关片段（最多约 4 条）。</div>
                      </div>
                    </SelectItem>
                    <SelectItem value="balanced">
                      <div>
                        <div className="font-medium">均衡</div>
                        <div className="text-xs text-gray-500">速度与数量兼顾，生成中等数量片段。</div>
                      </div>
                    </SelectItem>
                    <SelectItem value="quality">
                      <div>
                        <div className="font-medium">质量</div>
                        <div className="text-xs text-gray-500">优先质量与覆盖面，生成全部相关片段，耗时更长。</div>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={projectAudioFadeIn}
                  onChange={(e) => setProjectAudioFadeIn(e.target.checked)}
                  className="rounded"
                />
                启用音频淡入
              </label>

              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={projectAudioFadeOut}
                  onChange={(e) => setProjectAudioFadeOut(e.target.checked)}
                  className="rounded"
                />
                启用音频淡出
              </label>
            </div>

            <SheetFooter>
              <Button
                className="w-full"
                onClick={() => {
                  void handleApplyProjectSettings();
                  setSettingsSheetOpen(false);
                }}
                disabled={isApplyingSettings}
              >
                {isApplyingSettings
                  ? "应用中…"
                  : task.status === "completed"
                    ? "应用到全部片段"
                    : "保存设置"}
              </Button>
            </SheetFooter>
          </SheetContent>
        </Sheet>
      )}

      {/* Delete Task Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除生成任务</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除该生成任务吗？将永久删除所有片段且无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteTask} disabled={isDeleting} className="bg-red-600 hover:bg-red-700">
              {isDeleting ? "删除中…" : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Clip Confirmation Dialog */}
      <AlertDialog open={!!deletingClipId} onOpenChange={(open) => !open && setDeletingClipId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除片段</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除该片段吗？此操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deletingClipId && handleDeleteClip(deletingClipId)}
              className="bg-red-600 hover:bg-red-700"
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
