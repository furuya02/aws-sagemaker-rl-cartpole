# CartPole を題材にした理由

このプロジェクトが、なぜ Amazon SageMaker での強化学習ワークロードの題材として **CartPole** を選んだのかをまとめたドキュメント。

## 背景: Physical AI とは

Physical AI は「**物理世界を知覚し、推論し、動作する**」AI の総称。デジタル空間で完結する生成 AI の対極にある概念で、代表例は次のとおり:

- 自動運転車・ドローン
- ヒューマノイド / 産業ロボット
- スマート機器・工場制御

スタックは典型的に 3 層:

1. **Perception (知覚)**: センサー → 状態
2. **Decision (推論・制御)**: 状態 → 行動方針 ← **CartPole が扱う層**
3. **Actuation (動作)**: 行動命令 → モーター

## CartPole が表現しているもの

CartPole は「**観測 → 方策 → 行動 → 次の観測**」という閉ループ制御の最小単位。Physical AI の核となるサイクルを、最も簡潔に体現している。

| CartPole の構成要素 | Physical AI 一般での意味 |
|---|---|
| 観測 4 次元（位置・速度・角度・角速度） | センサーフュージョン、状態推定の縮小版 |
| 方策 (Policy ネットワーク) | エンドツーエンド制御の "脳" |
| 行動 2 択 (左 / 右) | アクチュエータ命令の抽象 |
| 報酬 +1/step | タスク目標の数値化（ロボット工学の最難所） |
| エピソード / 再起動 | シミュレータでの安全な試行 |
| 物理シミュレータ | 実世界の代替 (Sim 環境) |

## 実用課題とのアナロジー

「棒を倒さない」というタスクは、次の実用課題の **核心構造** と同じ:

- **二足歩行ロボット / 倒立振子型ロボット (Segway 等)** のバランス制御
- **ドローンの姿勢安定化**（機体傾きを推力で補正）
- **自動運転の車線維持**（横ずれ角度を操舵で補正）
- **産業ロボットアームの軌道追従**

これらは観測次元・行動次元・力学が複雑になるだけで、解いている問題の **構造そのものは同じ**。

## Physical AI 課題の難易度ラダー

Physical AI で扱う課題を難易度順に並べると:

```
L6: 実機デプロイ・Sim-to-Real (現場応用)
L5: 二足歩行 (Humanoid, Ant)
L4: ロボットアーム操作 (Manipulation, Reacher)
L3: 高次元観測 (画像入力 → CarRacing, Atari)
L2: 連続制御 (Pendulum, MountainCarContinuous)
L1: 離散制御の基礎 (CartPole) ← ★ここ★
```

CartPole は **L1 = 入口の最下段**。「閉ループの感覚」と「トレーニング〜デプロイのパイプライン」を最小コストで同時に押さえられる位置にある。

## もう一つの軸: MLOps パイプライン

CartPole そのものに加えて、本プロジェクトでは Physical AI の現場で必須となる **MLOps パターン** を一緒に動かしている:

```
[クラウドトレーニング]                              [推論サービング]
SageMaker Training Job  →  S3 (model.tar.gz)  →  SageMaker Endpoint
                                                    ↓
                                       実機ロボット / IoT 機器から API 呼び出し
```

実機ロボットでは Endpoint の代わりに **ONNX / TensorRT でエッジ推論** するのが定石だが、クラウド側パイプライン（トレーニング → モデル永続化 → 推論 API）の流れは Physical AI ワークロード全般で汎用。

## CartPole で扱わないもの

| 限界 | 次のステップ |
|---|---|
| 観測 4 次元の低次元 | 画像入力 → CNN policy |
| 2 値の離散行動 | 連続行動空間 (SAC, TD3) |
| 完全シミュレーション | **Sim-to-Real ギャップ**（摩擦・遅延・ノイズ・未知物体） |
| 単一タスク | マルチタスク・転移学習 |
| 短期エピソード | 長期計画・階層強化学習 |

特に **Sim-to-Real ギャップ** は Physical AI 最大の難所で、CartPole の中だけでは出会わない問題。

## なぜこの題材か (まとめ)

CartPole = **Physical AI の閉ループ制御の最小実装**。

- 「観測 → 方策 → 行動 → 観測」サイクルの感覚
- 「トレーニング → モデル永続化 → 推論 API」という MLOps パイプライン

この 2 つを **最小コスト・最小複雑度で同時に押さえられる入口** として機能する。ここから先は、観測次元（画像）、行動空間（連続）、ターゲット（実機 / Sim-to-Real）の 3 軸を順次広げていく段階に進む。

## 関連リンク

- [README.md](../README.md) / [README.ja.md](../README.ja.md) — プロジェクト概要・実行手順
- Gymnasium CartPole-v1: <https://gymnasium.farama.org/environments/classic_control/cart_pole/>
- Stable-Baselines3 PPO: <https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html>
