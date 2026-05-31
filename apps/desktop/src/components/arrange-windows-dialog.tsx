import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

export interface WindowArrangeSettings {
  startX: number
  startY: number
  width: number
  height: number
  col: number
  spaceX: number
  spaceY: number
}

export type WindowArrangeSettingKey = keyof WindowArrangeSettings

interface ArrangeWindowsDialogProps {
  open: boolean
  settings: WindowArrangeSettings
  isArranging: boolean
  onOpenChange: (value: boolean) => void
  onSettingChange: (key: WindowArrangeSettingKey, value: number) => void
  onSubmit: () => void
}

export function ArrangeWindowsDialog({
  open,
  settings,
  isArranging,
  onOpenChange,
  onSettingChange,
  onSubmit,
}: ArrangeWindowsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" showCloseButton={!isArranging}>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            onSubmit()
          }}
        >
          <DialogHeader>
            <DialogTitle>重排窗口</DialogTitle>
            <DialogDescription>Box 模式会按起点、尺寸、列数和间距重新排列当前浏览器窗口。</DialogDescription>
          </DialogHeader>

          <FieldGroup className="grid gap-3 sm:grid-cols-2">
            <WindowArrangeNumberField
              id="window-arrange-start-x"
              label="startX"
              value={settings.startX}
              onChange={(value) => onSettingChange("startX", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-start-y"
              label="startY"
              value={settings.startY}
              onChange={(value) => onSettingChange("startY", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-width"
              label="width"
              value={settings.width}
              min={400}
              onChange={(value) => onSettingChange("width", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-height"
              label="height"
              value={settings.height}
              min={900}
              onChange={(value) => onSettingChange("height", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-col"
              label="col"
              value={settings.col}
              min={1}
              onChange={(value) => onSettingChange("col", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-space-x"
              label="spaceX"
              value={settings.spaceX}
              onChange={(value) => onSettingChange("spaceX", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-space-y"
              label="spaceY"
              value={settings.spaceY}
              onChange={(value) => onSettingChange("spaceY", value)}
            />
          </FieldGroup>

          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" disabled={isArranging} />}>
              取消
            </DialogClose>
            <Button type="submit" disabled={isArranging}>
              {isArranging ? "正在重排" : "重排窗口"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

interface WindowArrangeNumberFieldProps {
  id: string
  label: string
  value: number
  min?: number
  onChange: (value: number) => void
}

function WindowArrangeNumberField({
  id,
  label,
  value,
  min,
  onChange,
}: WindowArrangeNumberFieldProps) {
  return (
    <Field className="min-w-0">
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        type="number"
        min={min}
        value={value}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
      />
    </Field>
  )
}
