# 参赛方向：HKMA-Aligned Agentic Compliance Co-pilot for Licensed Stablecoin Issuers

> 初版日期：2026-05-13
> 法规对齐重写：2026-05-14（依据 Cap 656《稳定币条例》+ HKMA AML/CFT Guideline 2025-08）

---

## 1. 个人目标

- **短期**：拿下赛道 4 名次（4,000 / 2,000 USDC）
- **长期**：积累 HSBC / 渣打 / 港币稳定币 / e-HKD 试点的可展示行业经验
  - 项目按 Cap 656 Schedule 2 s.10 + AML/CFT Guideline 各章节具体落地
  - 比赛交付物可直接演示一个 HKMA 合规闭环
  - 简历叙事：不是"做了 compliance demo"，而是"实现了 HKMA 持牌发行人合规义务的执行型 AI 副驾驶"

---

## 2. 项目重定位

| 维度 | 旧版（5-13） | 新版（5-14） |
|---|---|---|
| 定位 | 通用 AI 合规守门人 | HKMA 持牌稳定币发行人专属执行型 AI 合规副驾驶 |
| 法规依据 | 提及 HKMA 但未具体 | 每个 feature 可 trace 到 Cap 656 / AML Guideline 具体 paragraph |
| 目标用户 | 抽象 | Cap 656 s.15 下持牌发行人 |
| 卖点 | XAI + 多 agent | XAI 是法定义务（Para 5.7）、不是 nice-to-have |

### 核心思路（更新版）

> 每笔 USDC 转账广播前 → AI agent 实时拉链上链下数据（KYC / 钱包风险 / 制裁名单 / 对手方信誉 / 风险评分）
> → 自主决策（放行 / 拦截 / 路由隔离 / 触发人工复核）
> → 用 Circle Wallets + 智能合约执行（freeze / burn / blacklist）
> → 生成可审计的自然语言决策理由，满足 Para 5.7 法定书面化要求

**赛道 4（agent 自主执行链上动作）+ HKMA / VARA 双辖区可配置 = 比赛核心 + 简历杠杆**

---

## 3. 法规绑定（项目核心）

### 3.1 Cap 656《稳定币条例》— 法定授权钩子

| 条文 | 关键内容 | 项目意义 |
|---|---|---|
| s.3, s.4, s.5 | "specified stablecoin" 涵盖 USDC 等所有挂钩官方货币的稳定币；任何在港发行 / 挂钩 HKD 即 regulated activity | 目标用户清晰：所有 HKMA 持牌发行人 |
| s.8 | 无牌经营最高 HK$5M + 7 年监禁 | 不合规 = 刑事风险，发行人付费意愿高 |
| **Schedule 2 s.10** | 持牌人必须建系统防 ML/TF + 遵守 AMLO + HKMA 指引 | **整个项目的法定授权根源** |
| s.171 | HKMA 可发指引；违反指引虽不直接定罪，但法庭可采纳为证据 | 每个 feature 必须可 trace 到具体 paragraph |
| Schedule 4 | 不符合 minimum criteria 即吊销牌照 | s.10 = 牌照存续硬约束 |

### 3.2 AML/CFT Guideline — 章节-功能映射矩阵

每行 = 一个法规条款 → 一项功能 → 落在哪个 agent。监管检查时可一键导出对照表。

| 指引章节 / 段落 | 强制要求 | 对应功能 | 责任 agent |
|---|---|---|---|
| Ch 2 (Para 2.2-2.5) | 机构级风险评估（客户/地区/产品/渠道四维）+ 新产品上线前评估 | 风险评估配置中心 | Risk Assessment Agent |
| Ch 3 (Para 3.4-3.8) | CO / MLRO / 独立审计 / 员工筛查 / 培训 | 角色工作流 UI（demo 用占位） | Frontend |
| Para 4.3-4.18 | 4 类 CDD + RBA + EDD/SDD 切换 + HK$8,000 触发 | KYC pipeline | Risk Assessment Agent |
| **Para 4.11** | 必须采集 IP / 时间戳 / 地理位置 / 设备指纹 / 钱包地址 / 交易哈希 | 多源元数据采集 | Risk Assessment Agent |
| **Para 4.36** | 钱包所有权验证（micropayment / message signing） | 自动化所有权验证 flow | Risk Assessment Agent |
| Para 4.37 | 第三方托管钱包尽调 | 托管钱包 DD 模块 | Risk Assessment Agent |
| **Para 4.39** | unhosted wallet 强制筛查 + 高风险增强监控 / 限额 | 自托管钱包风险引擎 | Risk Assessment Agent |
| Para 4.22-4.24 | PEP 筛查（HK PEP + 境外 PEP + 国际组织 PEP + 亲属 + 密切关联人） | PEP 名单管道 | Compliance Decision Agent |
| **Para 5.4** | 区块链分析工具追踪 source/destination + 识别非法 / 制裁关联钱包 | 链上行为分析 | Risk Assessment Agent |
| Para 5.5 | 对外部区块链分析工具做尽调（质量 / 覆盖 / 准确 / 局限） | self-audit 模块 | 自评工具 |
| **Para 5.7** | 必须将"发现 + 调查背景 + 理由"书面化 | XAI 决策报告 | Report Generator Agent |
| **Para 5.10(c)** | 凭监管令冻结 / 销毁稳定币 | 链上 freeze / burn 执行 | On-Chain Executor Agent |
| Ch 6 (Para 6.5-6.16) | Travel Rule：≥ HK$8,000 全套信息；< HK$8,000 简化信息；立即 + 加密提交 | Travel Rule 中间件 | Compliance Decision + Executor Agent |
| Para 6.22-6.24 | 缺信息时 hold / return / 限制对手方关系 | 转账拦截器 | On-Chain Executor Agent |
| Para 6.32-6.39 | 转账对手方 DD + shell VASP 检测 + 不与 shell 交易 | 对手方 DD 模块 | Compliance Decision Agent |
| Para 6.40-6.42 | 与 unhosted wallet 转账的特殊要求 | 自托管钱包转账处理 | Compliance Decision Agent |
| **Para 7.2-7.5** | 制裁名单数据库（UNSCR + 港府宪报 + HKMA 通知）+ 三段筛查（发行 / 赎回 / 名单更新即时回扫 / 转账前筛所有相关方） | 制裁筛查引擎 + 自更新管道 | Compliance Decision Agent |
| Para 7.7 | 缺信息无法筛查时 hold 收款钱包 | 钱包冻结控制 | On-Chain Executor Agent |
| Ch 8 (Para 8.1-8.8) | STR 法定上报 + tipping-off 规避 + 后续冻结 / burn | STR 自动生成 + 上报 | Report Generator Agent |
| Ch 9 (Para 9.1-9.12) | 5 年记录保存 + 完整可重建审计链 | 审计日志数据模型 | 底层 infra |

### 3.3 关键合规常量

- **HK$8,000 门槛**：CDD 触发 / Travel Rule 全套信息 / 身份再验证（反复出现的法定阈值）
- **5 年保存**：业务关系结束或交易完成后再加 5 年
- **闭源 vs 开源 stablecoin model**（Para 5.9）：HKMA 区分对待，规则引擎需可切换

---

## 4. 多 Agent 架构（细化版）

```
ManagerAgent（编排 + 决策仲裁）
├── Risk Assessment Agent
│   ├── 客户 KYC（Para 4.3-4.18）
│   ├── PEP 识别（Para 4.22-4.24）
│   ├── 钱包所有权验证（Para 4.36）
│   ├── 钱包尽调（Para 4.37, 4.39）
│   ├── 元数据采集（Para 4.11：IP / 设备 / geo / 哈希）
│   └── 链上行为分析（Para 5.4：source / destination tracing）
│
├── Compliance Decision Agent
│   ├── 制裁 + PEP + 反恐 + 扩散融资名单筛查（Para 7.5）
│   ├── 规则引擎（HKMA / VARA 可切换）
│   ├── 转账对手方 DD（Para 6.32-6.39）
│   ├── shell VASP 检测（Para 6.39）
│   ├── LLM 推理 + 规则融合决策
│   └── 决策类型：放行 / 拦截 / 隔离路由 / 触发人工
│
├── On-Chain Executor Agent
│   ├── Circle Wallets 签名调用
│   ├── 转账拦截（Para 6.22-6.24）
│   ├── 钱包 hold（Para 7.7）
│   ├── 冻结 / burn（Para 5.10(c), 8.6）
│   └── 隔离路由（Circle Gateway）
│
└── Report Generator Agent
    ├── XAI 决策书面化（Para 5.7：背景 / 目的 / 证据链 / 规则引用）
    ├── STR 草稿生成（Ch 8）
    └── 5 年审计日志写入（Ch 9）
```

---

## 5. 差异化卖点（升级版）

### A. HKMA-aligned by design
每个决策可 trace 到具体 paragraph，监管检查时直接出"合规对照表"。其他参赛者做 generic compliance demo，我们做 regulator-grade reference implementation。

### B. 双辖区可配置（HKMA + VARA）
满足比赛地域（UAE / GCC）偏好 + 简历落点（HK 持牌发行人）。规则集独立配置文件，运行时切换。

### C. 可解释 AI（XAI）— 法定要求而非锦上添花
Para 5.7 强制持牌人将"发现 + 背景 + 理由"书面化。我们不是"加上"XAI，而是"实现"法定义务。

### D. Travel Rule 合规中间件
Ch 6 是持牌人最痛的工程难题。我们的中间件：
- 自动判别 HK$8,000 门槛
- 集成 IVMS 101 数据格式
- 缺信息自动 hold（Para 6.22-6.24）
- AI 驱动对手方 DD + shell VASP 检测（Para 6.32-6.39）

### E. 制裁名单自更新管道
持续抓取 UNSCR / 港府宪报 / Commerce and Economic Development Bureau，自动入库 + 历史回扫 + 触发再筛（Para 7.2-7.5）。

### F. Self-audit by regulator's own rubric
按 Para 5.5（HKMA 要求持牌人对外部分析工具做尽调的清单：质量 / 覆盖 / 准确 / 局限）反向自评我们自己的产品。"用监管的尺子量自己"是顶级可信度 signal。

### G. 链上执行权演示
Testnet 上演示 USDC freeze / burn / blacklist（Para 5.10(c) 明确点名期望持牌人具备的能力），其他参赛者大概率只演示监控不演示执行。

---

## 6. Circle 工具映射（精细版）

| 工具 | 用途 | 法规依据 |
|---|---|---|
| USDC | 全部交易结算币 | Cap 656 s.3 specified stablecoin |
| Circle Wallets | Agent 密钥管理 + 交易签名 + 钱包所有权验证 | Para 4.36，Schedule 2 s.9 |
| Circle Gateway | 拦截后路由到隔离地址 / 国库 | Para 5.10(b), 6.22 |
| CCTP + Bridge Kit | 跨链转账风险跟踪 + 拦截 | Para 5.4, Ch 6 |
| Nanopayments | Agent 调用大模型本身的内部计费 | （成本结构层） |

---

## 7. 三个月里程碑（章节对齐版）

### M1（第 1 个月）— 合规核心 PoC
- 架构定型 + 数据模型（满足 Ch 9 五年审计链）
- 单链 USDC 交易监控（Para 5.4）
- 制裁名单筛查引擎 v1（Para 7.5：UNSCR + 港府宪报）
- XAI 决策书面化（Para 5.7）
- Demo：单笔 USDC 转账被拦截，agent 输出自然语言理由
- Circle 接入：USDC + Wallets sandbox

### M2（第 2 个月）— 执行力扩张
- Travel Rule 中间件（Ch 6，含 HK$8,000 门槛判别 + IVMS 101 + 自动 hold）
- Unhosted wallet 风险引擎（Para 4.39, 6.40-6.42）
- 链上执行：USDC freeze / blacklist 演示（Para 5.10(c)）
- Circle Gateway 路由隔离
- 多 agent 编排成型（ManagerAgent → 4 SubAgent）

### M3（第 3 个月）— 双辖区 + 提交物
- VARA 规则集切换
- Para 5.5 self-audit 模块
- STR 自动生成 + 上报模拟（Ch 8）
- Demo URL 部署 + 视频 + 架构图 + GitHub README
- Circle Product Feedback 章节

---

## 8. 提交物清单（对照官方要求）

- [ ] Title + Short Description: "HKMA-Aligned Agentic Compliance Co-pilot for USDC Stablecoin Issuers"
- [ ] Track 4
- [ ] Circle Developer Account 注册
- [ ] Circle 产品勾选：USDC / Wallets / Gateway / CCTP+BridgeKit / Nanopayments
- [ ] Functional MVP（前端 + 后端 + Architecture Diagram）
- [ ] 视频 demo + presentation
- [ ] GitHub 仓库（含详细 README + 法规对照表）
- [ ] Demo 应用 URL
- [ ] Circle Product Feedback 章节

---

## 9. 简历叙事（赛后向 HSBC / 渣打投递时用）

> "Designed and shipped a regulator-grade agentic compliance system for licensed stablecoin issuers, implementing 20+ specific paragraphs of HKMA's AML/CFT Guideline (Aug 2025) and Cap 656 Schedule 2 s.10 across CDD, ongoing monitoring, travel rule, sanctions screening, and on-chain enforcement (freeze / burn / blacklist). Awarded [position] in the Circle Stablecoin Commerce Stack Challenge 2026."

关键加分点：
- 项目代码可现场对照法规 paragraph 逐项 demo
- 区分了 HKMA / VARA 两个辖区的规则集差异，证明对监管语义的精细理解
- 实现了 freeze / burn / blacklist 三个执行动作，远超事后审计型同类项目

---

## 10. 后续可选动作

- **A)** 出技术架构图（多 agent 数据流 + Circle 工具集成层 + 法规追溯标注）
- **B)** M1 第一周技术任务拆解（规则引擎 schema + Circle sandbox 接入 + 数据模型）
- **C)** HKMA / HSBC / 渣打 e-HKD 公开资料汇编（简历素材）
- **D)** 法规追溯矩阵导出（功能-paragraph-代码文件三列对照，用于 demo 视频字幕和监管沟通材料）
