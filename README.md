# OpenClaw AI Investment Committee

**玄武** — AI 投资委员会主席，统筹青龙、朱雀、白虎三位委员，做出资产配置决策。

## 目录结构

```
~/.openclaw/
├── openclaw.json.template          ← 脱敏配置模板（替换占位符后可运行）
├── README.md                       ← 本文件
├── .gitignore
│
├── workspace/                      ← 玄武（主席）
│   ├── AGENTS.md                   全局行为准则
│   ├── SOUL.md                     核心决策铁律
│   ├── IDENTITY.md                 主席身份
│   ├── USER.md                     董事会设定
│   ├── MEMORY.md                   长期记忆
│   ├── TOOLS.md                    工具笔记
│   ├── memory/                     日常记忆
│   └── skills/                     安装的技能
│
├── workspace-qinglong/             ← 青龙（保守派）
├── workspace-zhuque/               ← 朱雀（成长派）
├── workspace-baihu/                ← 白虎（激进派）
│
└── plugin-skills/                  ← 飞书/蓝信插件技能（符号链接）
```

## 环境变量

`openclaw.json.template` 中的占位符需要替换为实际值才能运行：

| 占位符 | 说明 | 来源 |
|---|---|---|
| `$GATEWAY_TOKEN` | OpenClaw Gateway 管理界面访问令牌 | 生成随机字符串 |
| `$MOONSHOT_API_KEY` | Moonshot KIMI API Key | https://platform.moonshot.cn |
| `$FEISHU_MAIN_APP_ID` | 飞书应用 App ID（玄武 Bot） | https://open.feishu.cn/app |
| `$FEISHU_MAIN_APP_SECRET` | 飞书应用 App Secret（玄武 Bot） | 同上 |
| `$FEISHU_QINGLONG_APP_ID` | 飞书应用 App ID（青龙 Bot） | 同上 |
| `$FEISHU_QINGLONG_APP_SECRET` | 飞书应用 App Secret（青龙 Bot） | 同上 |
| `$LANSENGER_APP_ID` | Lansenger 应用 App ID | Lansenger 控制台 |
| `$LANSENGER_APP_SECRET` | Lansenger 应用 App Secret | Lansenger 控制台 |
| `$PUBLIC_IP` | 服务器公网 IP | 服务器提供 |
| `$BASE_PATH` | Control UI 路径前缀 | 生成随机字符串 |

### 生产部署

```bash
# 复制模板为实际配置
cp openclaw.json.template openclaw.json

# 使用 sed 替换占位符（示例）
sed -i 's/\$GATEWAY_TOKEN/your-actual-token/g' openclaw.json
sed -i 's/\$MOONSHOT_API_KEY/sk-your-key/g' openclaw.json
# ... 依次替换所有占位符
```

## Git 安全策略

本仓库通过以下措施保护敏感信息：

| 措施 | 说明 |
|---|---|
| `openclaw.json.template` | 生产配置的脱敏版本，原生 `openclaw.json` 已 gitignore |
| `.gitignore` | 排除 `credentials/`、`agents/`（含 API Key）、`*.jsonl`（聊天历史） |
| 运行时产物 | 所有缓存、日志、session 数据已 gitignore |

## 使用方式

1. 替换 `openclaw.json.template` 中的占位符为实际值
2. 复制为 `openclaw.json`
3. 确保各 Agent 的 workspace 目录存在
4. 启动 OpenClaw

## 委员会工作流程

1. **主席（玄武）** 接收议题
2. 通过 sessions_send 召集各委员输出独立分析
3. 收集、对比、识别冲突与共识
4. 综合评级，做出最终决策
5. 向董事会汇报

### 决策原则

- **风控优先**：保守派与其他派别冲突时倾向保守建议
- **要求共识**：严重分歧时输出"观望/等待更多信号"
- **尊重少数意见**：在决策中记录风险提示
