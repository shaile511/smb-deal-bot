{{- define "smb-deal-bot.labels" -}}
app.kubernetes.io/part-of: smb-deal-bot
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
