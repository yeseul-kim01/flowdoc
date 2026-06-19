# FlowDoc 팀 분담 & 협업 계획

## 목표

백엔드 내부 흐름을 "Swagger처럼" 시각화한다. 단, **두 프레임워크에서 동일한 기능**을:

- **Spring Boot** 에 붙이는 버전 — **kys**
- **FastAPI** 에 붙이는 버전 — **jch**

기능은 같다. OpenAPI 스펙 하나에 Swagger UI 하나인 것처럼, FlowDoc도 **스펙 하나 · UI 하나**를
공유하고 **수집기(collector)만 언어별로** 둔다. 이게 이 프로젝트의 처음부터의 설계다
([flowdoc-기획안.md](flowdoc-기획안.md) §7, §12).

```
[Spring Boot 수집기 — kys] ─┐
                            ├─→  [공유 스펙 (flowdoc.json)]  ─→  [공유 UI (ui/)]
[FastAPI 수집기 — jch]     ─┘          단일 진실 원천              언어 중립 뷰어
```

---

## 분담

### kys — Spring Boot 수집기 (`flowdoc-java/`)
"Spring Boot 내부용 Swagger." 이미 v0.2 진행 중.
- `flowdoc-scanner` (JavaParser + SymbolSolver → 스펙)
- `flowdoc-annotations` (`@FlowEntry`, `@Guarded`, …)
- `flowdoc-core` (스펙 모델 + JSON 직렬화)
- `flowdoc-spring-boot-starter` (`/flowdoc` 라이브 엔드포인트)

### jch — FastAPI 수집기 (`flowdoc-python/`)
"FastAPI 내부용 Swagger." kys 산출물과 **동일 기능 · 동일 스펙**.
- `scanner` — Python `ast`로 함수·호출 추출 → 스펙
- `annotations`(데코레이터) — `@flow_entry`, `@guarded`, `@flow_external`, `@flow_ignore`, `@flow_doc`
- `core` — 스펙 dataclass + JSON 직렬화 (flowdoc-core의 파이썬 대응물)
- FastAPI 통합 — `/flowdoc` 라우터 마운트 (flowdoc-spring-boot-starter의 대응물)

권장 패키지 레이아웃(확정 아님, jch 재량):
```
flowdoc-python/
  flowdoc/
    annotations.py   # 데코레이터
    spec.py          # 스펙 dataclass + (de)serialize  ← spec 스키마에 conform
    scanner.py       # ast 워커 → 스펙
    fastapi.py       # /flowdoc 라우터 (뷰어 + 스펙 서빙)
    __main__.py      # CLI: python -m flowdoc <src> <out.json>
  examples/<fastapi 데모>
  pyproject.toml
```

---

## 공동 소유 — 둘이 합의해서만 바꾼다

이 둘은 **계약**이다. 한쪽이 마음대로 바꾸면 패리티가 깨진다.

| 공유 자산 | 의미 | 규칙 |
|---|---|---|
| `spec/flowdoc-0.1.schema.json` | 단일 진실 원천. 양쪽 산출물이 여기 conform | 변경 시 **양측 합의 + 양쪽 동시 반영** |
| `ui/` | 공유 뷰어. 언어 중립 | **포크 금지.** 한쪽이 고치면 양쪽 영향 → 함께 리뷰 |

- 스펙에 부족한 필드를 발견하면 → 혼자 우회하지 말고 **스펙을 함께 확장**한다.
- 스펙은 `language`/`framework` 필드로 출처를 구분한다 (`java`/`spring-boot`, `python`/`fastapi`).
  UI는 출처를 몰라도 똑같이 그린다 — 그게 정상.

---

## 기능 패리티 매핑 (같은 개념, 다른 표현)

jch의 FastAPI 수집기가 kys의 Spring 수집기와 "동일 기능"이 되려면 아래를 같은 스펙 모양으로 뽑아야 한다.

| 개념 | Spring (kys) | FastAPI (jch) |
|---|---|---|
| 진입점 + 이름 | `@FlowEntry("tag")` | `@flow_entry("tag")` |
| 라우트 인식 | `@GetMapping`/`@PostMapping`/`@RequestMapping` | `@app.get`/`@router.post` + `APIRouter(prefix=)` |
| 트랜잭션 경계 | `@Transactional` | `async with session.begin()` / 선언 `@transactional` (Python엔 표준이 없으니 컨텍스트매니저·데코레이터 인식) |
| 동시성 가드 | `@Guarded(resource, permits)` | `@guarded(resource=, permits=)` |
| 비동기 후처리 | `@Async` | `async def` / FastAPI `BackgroundTasks` |
| 데이터 경계 | `@Repository` / JpaRepository | SQLAlchemy 모델·세션 / repository 클래스 |
| 외부 경계 | `@FlowExternal` | `@flow_external` |
| 노이즈 제거 | `@FlowIgnore` | `@flow_ignore` |
| 설명 | Javadoc / `@Operation` / `@FlowDoc` | docstring / 라우트 `summary=`·`description=` / `@flow_doc` |
| 의존성 주입 | 생성자 주입 | `Depends()` |
| 보안 게이트 | `@PreAuthorize` 등 | `Depends(get_current_user)` / `Security()` |
| 호출 해석 | JavaParser SymbolSolver | `ast` (+ 옵션 타입추론). 못 풀면 **버린다 — 추측 금지** |
| 라이브 엔드포인트 | `flowdoc-spring-boot-starter` `/flowdoc` | FastAPI 라우터 mount `/flowdoc` |

> 메타 원칙은 언어 무관하게 동일: **파서가 읽을 수 있는 건 사람에게 안 시키고, 못 푸는 호출은
> 날조하지 않는다.** Python은 동적 타입이라 호출 해석이 더 어렵다 — 그만큼 못 풀면 버리거나
> 선언 힌트(`@flow_resolves` 등)에 기댄다 (§11).

---

## "동일 기능"의 정의 = 같은 UI에 똑같이 뜬다

통합 성공 기준:

1. kys: `examples/coupon-rush` (Spring) → `flowdoc.json`
2. jch: `examples/<fastapi 동등 데모>` → `flowdoc.json`
3. **둘을 같은 `ui/index.html`로 열었을 때** 같은 모양 — tx 레일, 가드 배지, async 분리,
   외부 경계, 설명 — 으로 보이면 패리티 달성.
4. 회귀 방지: 양쪽 예제의 `flowdoc.json`을 `spec/flowdoc-0.1.schema.json`으로 검증.

권장 진행 순서(양쪽 공통):
1. **스펙부터 읽는다** (`spec/` + 기획안 §8) — 둘의 공통 언어.
2. 최소 흐름(진입점→서비스→repo)을 먼저 스펙으로 뽑아 UI에 띄운다.
3. 기능을 하나씩 패리티로 채운다: tx → guard → async → external → 설명.
4. 스펙에 부족한 게 보이면 → 함께 확장.

---

## 협업 워크플로우 — 패리티 이슈 주도

두 수집기는 같은 스펙·UI를 공유하므로, 기능이 **한쪽에만 있으면 패리티가 깨진다.** 그래서
**한쪽이 기능을 구현하면 → 패리티 이슈를 열고 → 반대편이 미러한다.** 양방향으로 똑같이.

```
 ① kys: Spring 에 기능 구현 & 머지
        │
        ▼
 ② 🔁 Parity 이슈 생성  ──(산출 스펙 모양 + 대응 힌트 명시)──┐
        │                                                  │
        ▼                                                  ▼
 ③ jch: FastAPI 에 같은 스펙 출력 목표로 구현        (반대 방향도 동일:
        │                                            jch 구현 → 이슈 → kys 미러)
        ▼
 ④ 완료: 같은 ui/index.html 에서 동일하게 렌더 → 이슈 close
```

**단계**
1. **구현 & 머지** (한쪽). 끝나면 미루지 말고 바로 이슈를 연다.
2. **🔁 Parity 이슈 생성** — 핵심은 두 칸이다:
   - *산출되는 스펙 모양* — 이 기능이 `flowdoc.json`에 만드는 노드/엣지/필드. **패리티의 측정 기준.**
   - *프레임워크 대응 힌트* — 위 패리티 표 기준으로 반대편이 무엇을 인식해야 같은 출력이 나오나.
3. **반대편이 픽업** — "같은 스펙 출력"을 목표로 구현. UI는 공유라 안 건드린다.
4. **완료 기준** — 반대편 예제의 `flowdoc.json`이 스키마를 통과하고, **같은 UI에서 동일하게** 보이면 close.

**스펙 변경이 끼면** (shared contract): 그 패리티 이슈는 `spec` 라벨을 달고, `spec/`·`ui/` 변경은
**양측 합의 + 양쪽 동시 반영** 후에 닫는다. 한쪽만 반영하면 패리티가 다시 깨진다.

### 이슈 템플릿 & 라벨

템플릿은 [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/)에 있다:
- **🔁 Parity** (`parity.yml`) — 위 워크플로우의 주인공
- **✨ Feature / Idea** (`feature.yml`) — `docs/ideas.md` 후보 제안
- **🐞 Bug** (`bug.yml`)

권장 라벨(미리 GitHub에 만들어 둘 것): `parity`, `area:spring`, `area:fastapi`, `spec`, `ui`,
`enhancement`, `bug`.

---

## PR / 리뷰 규칙

| 변경 영역 | 주 담당 | 리뷰 |
|---|---|---|
| `flowdoc-java/` | kys | kys |
| `flowdoc-python/` | jch | jch |
| `spec/`, `ui/` (공유 계약) | — | **양측 모두** |

공유 계약(spec·ui)을 건드리는 PR은 반드시 양쪽이 리뷰한다.
