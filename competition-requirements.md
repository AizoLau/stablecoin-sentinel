# Stablecoin Commerce Stack Challenge — 比赛要求

> 来源：https://challenges.ignyte.ae/competition/4B436318-C737-F111-9A49-6045BD14D400
> 整理时间：2026-05-13

## 基本信息

| 项目 | 内容 |
|---|---|
| 主办方 | Ignyte（迪拜 DIFC 旗下创业生态平台） |
| 技术赞助 | Circle + Arc（Circle 自家 L1 区块链） |
| 形式 | 线上虚拟比赛 |
| 周期 | 3 个月 |
| 链上环境 | 仅限测试网，仅供教学和 demo 用途 |
| 区域聚焦 | UAE / GCC 海湾国家（但接受全球开发者） |

## 为何用 Arc

Arc 是 Circle 的可编程 L1 区块链：
- USDC 计价的可预测手续费
- 确定性 finality（实时金融工作流）
- 智能合约编排支付
- Circle 基础设施原生支持跨链 USDC

参考：Arc docs / Circle docs / Arc sample apps。

## 四大赛道

| # | 赛道 | 1 名 | 2 名 |
|---|---|---|---|
| 1 | Cross-Border Payments & Remittances（跨境支付汇款） | 5,000 USDC | 3,000 USDC |
| 2 | SME Trade Finance & Working Capital（SME 贸易融资） | 5,000 USDC | 3,000 USDC |
| 3 | Real World Asset Tokenization with Embedded Compliance | 3,000 USDC | — |
| 4 | Agentic Economy Experience | 4,000 USDC | 2,000 USDC |

总奖金池约 25,000 USDC。

### 赛道 1：UAE 跨境支付 / 汇款

- 重点：UAE 高外籍劳工汇款走廊，瞬时低费率
- 示例：透明费率汇款 App / marketplace 全球结算 / 稳定币发薪 / "付 AED 结算 USDC"

### 赛道 2：SME 贸易融资 / 营运资金

- 重点：发票、托管、自动结算、可验证支付历史
- 示例：应收账款 factoring / 进出口里程碑托管 / 采购单融资 / SME "信用护照"

### 赛道 3：RWA 代币化 + 嵌入式合规

- 重点：固定收益、Sukuk、地产、合规基础设施
- 示例：分割化债券 / 可编程分润 Sukuk / REIT 租金分发 / 链上 KYC/AML 限制

### 赛道 4：Agentic Economy（AI 代理经济）— 我们选这个

- 重点：AI agent 自主研究、谈判、执行链上交易
- 官方示例：
  - AI agent 自主发现并完成 USDC 结算购买
  - 订阅自动续费 / 预算控制
  - 多对手方自动商户结算
  - 跨钱包跨链路由的 AI 忠诚度计划
  - 按次推理付费的 AI 代理（pay-per-inference）
  - 内容/API 按秒/按事件流式支付

## Circle 工具栈

**普通可用（无需申请）**：
- USDC — 主结算币
- Circle Wallets — 嵌入式钱包，对非 Web3 用户友好
- Circle Gateway — 国库路由 / 多方流转
- CCTP + Bridge Kit — USDC 跨链
- Nanopayments — 高频亚分钱级支付（赛道 4 推荐）

**Enterprise / Gated（需申请，可能不批）**：
- USYC — 收益型现金管理
- StableFX — FX 感知多币种结算

申请方式：填写官方表单后发邮件到 `customer-support@circle.com`，主题 `Circle Hackathon - USYC or StableFX testnet request`。
未拿到访问权时，做"概念性 / 架构层"集成不扣分。

## 提交清单（每项必交）

1. Title + Short Description
2. Track（选 1 个赛道）
3. Circle Developer Account 邮箱（在 console.circle.com/signup 注册）
4. 使用的 Circle 产品勾选：USDC / Wallets / Gateway / CCTP+BridgeKit / USYC / StableFX / Nanopayments
5. **Functional MVP + 架构图**：必须有可跑的前端 + 后端 + architecture diagram
6. **视频 demo + presentation**：精炼讲清核心功能 + 如何用 Circle 工具，配详细文档
7. **GitHub 仓库链接**：含详细 README（如何 setup、如何对接 Circle 工具）
8. **Demo 应用 URL**（公开可访问的 demo 平台地址）
9. **"Circle Product Feedback" 章节**（必含、标题明确），需写：
   - 为什么选这些 Circle 产品
   - 开发中哪些好用
   - 哪些可以改进
   - 给 Circle 让产品/DX 更顺滑的建议

## 关键注意点

- 测试网项目，禁止真实资金 / 主网部署
- 必须有可运行的 MVP，不是纸面方案
- 视频 + 架构图 + GitHub README + Product Feedback 章节是硬指标
- 赛道 1 和 2 奖金最高（合计 8,000 USDC）且 UAE 区域属性强
- 赛道 4 适合有 AI 背景的开发者

## 待确认信息（页面 SPA 公开内容里未列出）

- 报名截止日 / 提交截止日 / 各阶段时间节点
- 评审打分细则（rubric 权重）
- 团队人数上限 / 国籍限制 / 年龄限制
- 评审委员名单

→ 登录 Ignyte 平台后在 competition 页面查 Timeline / Rules / FAQ，或私信官方确认。
