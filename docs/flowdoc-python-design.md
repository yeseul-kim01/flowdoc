# FlowDoc 파이썬 수집기 — 설계 (design.md)

- 대상: `flowdoc-python` (자바 `flowdoc-scanner`의 파이썬 대응)
- 위치(예정): `flowdoc/flowdoc-python/` (멀티 언어, `flowdoc-java`와 형제)
- 출력 계약: `spec/flowdoc-0.1.schema.json` (언어 중립, 그대로 준수)
- 작업 형태: 팀 작업 (본 문서는 chat 설계 단계, 구현은 Code에서 진행)

---

## 1. 목적과 범위

파이썬 백엔드 소스를 **정적으로 파싱**해 자바 수집기와 동일한 `flowdoc.json`을 생성한다. 실행 중인 앱에 붙지 않고 `.py` 소스만 읽는다.

### MVP 범위 (이번 산출물)

- 노드: 함수·메서드 단위 (`auto.params`, `auto.returns`, `auto.annotations`, `declared.description` 포함)
- 간선: 정적으로 해소 가능한 호출 관계
- 시퀀스 + 트리거 디스크립터 (PR #1 정합성, 13절):
  - declared: `@flow_entry` 명시 (`source="declared"`)
  - auto: FastAPI 라우트 데코레이터 자동 감지 (`source="auto"`, `trigger.kind="http"`)
  - 기존 BOOK 코드에는 `@flow_entry`가 없으므로, auto 라우트 감지가 없으면 시퀀스가 0개가 됨 → MVP 필수

### 비범위 (다음 단계로 분리)

- 트랜잭션 경계(`markers.transaction`), 가드(`guards`), async/event 간선
- scheduled/messaging/websocket 트리거 종류 (BOOK 사용 시에만 추가)
- accessor 노이즈 필터, jedi 기반 타입 추론
- 런타임 트레이스(`traces`) — 정적 스캔에서는 항상 `[]`

핵심 가치 검증: 생성한 스펙을 기존 FlowDoc UI에 넣었을 때 호출 흐름이 그려지는가.

---

## 2. 아키텍처 / 자바 대응

```
[python src tree] → [정적 스캐너 (ast)] → [flowdoc.json] → [기존 FlowDoc UI]
                         언어만 파이썬, 스펙·UI는 공유
```

| 자바 | 파이썬 (본 프로젝트) | 계층 |
|---|---|---|
| flowdoc-scanner (JavaParser + SymbolSolver) | `ast` 모듈 기반 스캐너 | 핵심 |
| 표준 어노테이션 인식 (`@PostMapping`, `@Transactional`) | 데코레이터·패턴 인식 (다음 단계) | auto |
| `@FlowEntry` 등 어노테이션 | `@flow_entry` 등 데코레이터 | declared |
| flowdoc-spring-boot-starter (`/flowdoc` 서빙) | FastAPI 라우터 (다음 단계, 선택) | 서빙 |
| flowdoc.json · ui | 동일 | 공유 |

---

## 3. 입출력 계약

### 입력

- `src_root`: 스캔할 파이썬 소스 루트 디렉터리
- 출력 경로: `flowdoc.json` 파일 경로
- 기본 제외: `__pycache__`, `.venv`, `venv`, `site-packages`, `tests`, `migrations` (설정 가능)

### 출력 (스펙 0.1 최상위)

```json
{
  "flowdoc": "0.1",
  "source": { "language": "python", "framework": "fastapi", "collector": "static" },
  "nodes": [ ... ],
  "edges": [ ... ],
  "sequences": [ ... ],
  "guards": [],
  "traces": []
}
```

생성 직후 `jsonschema`로 스펙 검증 후 직렬화한다. 검증 기준 스키마는 **PR #1로 확장된 버전**을 사용한다(`sequence`에 `source`·`trigger` 추가, `flowdoc` 버전 상수는 여전히 `"0.1"`). PR #1 머지 전이면 팀원 브랜치 `feat/trigger-entry-detection`의 스키마를, 머지 후면 `main`의 스키마를 기준으로 한다.

---

## 4. 데이터 모델

스펙 필드를 그대로 담는 dataclass를 정의한다(자바 `flowdoc-core`의 record 대응). 직렬화 시 `None`·빈 항목은 스펙에 맞게 정리한다.

### 노드 id 규칙 (자바 `FQCN#method(SimpleParamTypes)`의 파이썬 판)

형식: `{한정 소유자}#{이름}({파라미터 타입})`

- 메서드: `app.domain.auth.service.AuthService#login(LoginRequest)`
  - 한정 소유자 = 모듈 경로 + 클래스명 (모듈 경로는 `src_root` 기준 상대 경로를 점 표기로 변환)
- 모듈 함수: `app.utils.token#create_token(UUID)`
  - 한정 소유자 = 모듈 경로 (클래스 없음)

규칙:
- `self` / `cls`는 파라미터에서 제외 (자바에 없음)
- 파라미터 타입은 타입힌트의 소스 표기를 사용 (`Optional[User]` → `"Optional[User]"`, `ast.unparse`)
- 타입힌트가 없는 파라미터는 자리표시자 `_` 사용 (id 안정성·arity 보존) — 열린 결정 11-a

### 노드 필드 매핑

| 스펙 필드 | 파이썬 출처 |
|---|---|
| `id`, `simpleName`, `owner`, `kind="method"` | 4절 규칙 / 정의명 / 클래스명 |
| `location.file`, `.line`, `.module` | 파일 경로(상대), `def` 라인, 모듈 점 표기 |
| `auto.params[].name/type` | 시그니처(타입힌트, `self`/`cls` 제외) |
| `auto.returns.type` | 반환 타입힌트 (없으면 `null`) |
| `auto.annotations[].name/attributes` | 데코레이터 이름·인자 (있는 그대로 나열) |
| `declared.description`, `paramDocs` | 함수 docstring (요약/파라미터 파싱) |
| `markers` | MVP에서는 미설정(다음 단계) |

`auto.annotations`와 `declared.description`은 같은 AST 순회에서 거의 무비용으로 채워지므로 MVP에 포함한다(마커 해석과는 별개).

### 간선 필드 매핑

| 스펙 필드 | 값 |
|---|---|
| `from` | 호출이 일어난 노드 id |
| `to` | 해소된 대상 노드 id |
| `callType` | MVP에서는 `"sync"` 고정 |
| `site.file`, `.line` | 호출 위치 |
| `resolution` | 6절 해석 결과 |

---

## 5. 처리 파이프라인

1. **수집(discovery)**: `src_root` 순회, 제외 규칙 적용해 `.py` 파일 목록 확보
2. **파싱(parse)**: 파일별 `ast.parse(source, filename)` → 모듈 AST. 파일 경로 → 모듈 점 표기 산출
3. **정의 색인(index, 1차 순회)**: 모든 함수·메서드 정의를 수집해 노드 후보 + 조회 인덱스 구성
   - `(모듈, 한정명)` → 정의
   - `단순명` → 정의 목록 (이름 폴백용)
   - 모듈별 import 표 (별칭 → 모듈/대상)
4. **노드 생성(nodes)**: 정의에서 `auto`/`declared`/`location` 채워 노드 객체 생성
5. **간선 해소(edges, 2차 순회)**: 각 함수 본문의 `ast.Call`을 찾아 6절 알고리즘으로 대상 해소
6. **시퀀스·트리거 생성(sequences)**: 진입점을 두 경로로 감지 (13절 규칙)
   - declared: `@flow_entry("tag")` → `source="declared"`, `tag`=인자값
   - auto: FastAPI 라우트 데코레이터(`@app.post`, `@router.get` 등) → `source="auto"`, `tag`=`{owner}.{simpleName}`, `trigger.kind="http"`
   - 한 함수에 둘 다 있으면 declared 우선, `trigger`는 라우트에서 채움
7. **조립·검증·출력**: 스펙 dict 조립 → `jsonschema` 검증 → `flowdoc.json` 기록

색인을 먼저 만들고(3) 간선을 나중에 푸는(5) 2-pass 구조여야 전방 참조(아직 정의 안 본 대상 호출)를 해소할 수 있다.

---

## 6. 심볼 해석 알고리즘 (핵심)

확정된 방향: **ast + 타입힌트 + 이름 폴백** (jedi는 다음 단계 폴백 후보).

호출식 종류별 처리:

- `name(...)` (이름 호출): import 표 → 모듈/지역 스코프 순으로 대상 정의 탐색
- `obj.method(...)` (속성 호출): `obj`의 타입을 아래 순서로 판별
  1. `self.method` → 같은 클래스(해소되면 프로젝트 내 상위 클래스 포함)에서 탐색
  2. `obj`가 타입힌트 있는 파라미터/지역변수 → 그 타입이 가리키는 프로젝트 내 클래스의 메서드
  3. `obj`가 모듈/임포트 이름 → import 표로 해소

대상을 못 좁힐 때 폴백: 인덱스에서 `method` 단순명으로 검색.

### resolution 값 매핑 (스펙 enum)

| 상황 | resolution | 간선 |
|---|---|---|
| self / 타입힌트 / import로 단일 대상 확정 | `concrete` | 생성 |
| 타입 불명, 단순명 후보가 정확히 1개 | `single-impl` | 생성 |
| 타입 불명, 단순명 후보 2개 이상 | `ambiguous` | **버림** (추측 금지, DEBUG 로그) |
| 대상이 프로젝트 밖 (stdlib·3rd-party) | — | **버림** (다음 단계: 경계 노드) |
| `runtime-confirmed` | — | 정적에서 미사용 (런타임 에이전트 전용) |

원칙은 자바와 동일하다: **모르면 추측하지 않고 버린다.** 끊긴 간선 비율이 해석 정확도의 지표가 되며, 이 비율이 높으면 그때 jedi 폴백 도입을 검토한다.

---

## 7. Edge Case

- `self.m()` / `cls.m()` / classmethod·staticmethod
- 모듈 함수 vs 메서드 (id 형식 분기, `self` 제외)
- 수신자 타입힌트 없음 → 이름 폴백 (단일 `single-impl`, 다중 버림)
- 별칭 임포트 (`from x import y as z; z()`)
- 프로젝트 밖 호출 (`httpx.get`, `session.query`) → 버림
- 데코레이터로 감싼 함수 (`@router.post` 등) — 정의는 노드, 데코레이터는 `auto.annotations`에 기록
- 중첩 함수·lambda → MVP는 lambda 제외, 중첩 함수 제외(열린 결정 11-b)
- 재귀(자기 호출) → 간선만 기록(순회 아님, 무한루프 없음)
- accessor/property/dunder → MVP는 모두 포함, 노이즈 필터는 다음 단계(자바 v0.2와 동일 순서)
- `async def` → 일반 함수처럼 노드화, MVP는 `callType="sync"`
- 체인 호출 `a().b()` → 반환 타입 불명 시 버림
- star import / 조건부 import → 이름 폴백만
- 제네릭 타입힌트 (`List[Order]`) → 타입 문자열은 소스 그대로, 매칭은 내부 클래스명 추출
- 파싱 실패 파일 (구문 오류·py2) → 구체 예외 포착, WARN 로그 후 해당 파일 건너뜀

---

## 8. 모듈 구조 / CLI

자바 `annotations / core / scanner` 분리를 파이썬 패키지로 대응:

```
flowdoc-python/
  flowdoc/
    decorators.py      # @flow_entry 등 (MVP는 @flow_entry, 메타데이터 부착·이름 인식)
    spec.py            # Node/Edge/Sequence/Spec dataclass + 직렬화 (core 대응)
    scanner/
      discovery.py     # 파일 수집
      parser.py        # ast → 정의 + 인덱스 (1차)
      resolver.py      # 호출 해소 (2차)
      builder.py       # 스펙 조립 + 검증
      cli.py           # 진입점
  tests/
  pyproject.toml
  requirements.txt
```

실행(자바 `:flowdoc-scanner:run --args="src out"` 대응):

```bash
python -m flowdoc.scanner <src_root> <out.json>
```

---

## 9. 의존성 · 로깅 · 코딩 표준

- 런타임: Python (3.11+), `ast`는 표준 라이브러리, 스펙 검증용 `jsonschema`
- 개발: `pytest`, `ruff`, `mypy`
- 모든 의존성은 정확한 버전 명시 + `requirements.txt`/`pyproject.toml` 동반 (구현 단계에서 pin)
- 로깅: `print` 금지, 표준 `logging` + 커스텀 `SUCCESS` 레벨. DEBUG(호출 해소)·INFO(파일 수)·SUCCESS(스펙 생성)·WARN(파싱 실패·버린 간선)
- 모든 함수 Type Hint·public 함수 Docstring, 구체 예외 타입, 매직넘버 상수화
- 테스트: 정상 케이스 1 + 예외 케이스 1 이상 (핵심 로직별)
- 경로·키 등 개인정보는 플레이스홀더 + TODO

---

## 10. 다음 단계 (post-MVP)

1. 트리거 종류 확장: scheduled(APScheduler/Celery beat → `{cron}`), messaging(Celery/Kafka 컨슈머 → `{broker, destination}`), websocket — BOOK 사용 패턴에 맞춰 추가
2. 트랜잭션 경계: 파이썬 관례 매핑 (SQLAlchemy 세션 / `@transaction.atomic` / 선언 데코레이터 중 택1) → `markers.transaction`
3. async/event 간선: 백그라운드 태스크·이벤트 발행 패턴
4. 가드: `@guarded` → `guards`
5. accessor 노이즈 필터
6. 해석 정확도 미달 시 jedi 폴백 도입 (정확도 향상 대 스캔 시간 비교)

---

## 11. 열린 결정 (확정 필요)

- **11-a** 타입힌트 없는 파라미터의 id 자리표시자: `_` 사용으로 충분한가
- **11-b** 중첩 함수 포함 여부: MVP 제외 제안
- **11-c** 테스트 대상 앱: **확정 — 기존 FastAPI 프로젝트 BOOK(`~/Documents/Dev/Work/BOOK`) 스캔.** 단위 테스트용 소형 픽스처는 별도 유지(정답 입력으로 정확성 검증)
- **11-d** 대상 파이썬/프레임워크 버전 고정값

---

## 12. PR #1 정합성 (팀원 트리거 표준 반영)

팀원 PR #1(`feat/trigger-entry-detection`, `feat(scanner): auto-detect entry triggers with a language-neutral trigger descriptor`)이 공유 스펙을 확장했다. 자바·파이썬 공용 계약이므로 파이썬 수집기도 동일 형태로 출력한다.

- `sequence`에 `source`(`declared`|`auto`)와 `trigger`(`{kind, label, detail}`) 추가
- `trigger.kind` enum: `http` / `scheduled` / `messaging` / `event` / `websocket`
- UI는 `trigger.kind`·`label`로만 렌더링. 프레임워크 어노테이션 이름은 노출 안 함
- `Trigger` 주석에 FastAPI 매핑이 명시되어 있어, 파이썬은 FastAPI를 이 shape로 매핑만 하면 됨

자바와의 분담: 도구·언어는 서로 다르고(자바 JavaParser, 파이썬 ast), 맞추는 것은 **출력 스펙(특히 trigger 형태)**이다.

## 13. 진입점·트리거 규칙 (자바 출력과 동일하게)

라벨·detail·tag 표기를 자바 출력과 정확히 일치시켜 공유 UI가 동일하게 렌더링되게 한다.

| 진입 종류 | 감지 | source | trigger.kind | label | detail |
|---|---|---|---|---|---|
| 명시 | `@flow_entry("tag")` | `declared` | 라우트 있으면 http | (라우트에서) | (라우트에서) |
| HTTP | `@app.<verb>` / `@router.<verb>("/path")` | `auto` | `http` | `"<VERB> /path"` (verb 대문자) | `{verb, path}` |
| 스케줄(post-MVP) | APScheduler/Celery beat | `auto` | `scheduled` | `"Scheduled · <cron>"` | `{cron}` |
| 메시징(post-MVP) | Celery/Kafka 컨슈머 | `auto` | `messaging` | (브로커·대상) | `{broker, destination}` |

tag 규칙: declared는 `@flow_entry` 인자값, auto는 `{owner}.{simpleName}` (자바 동일: 예 `CouponController.remaining`).

자바 실제 출력 예(참고):

```json
{ "tag": "CouponController.remaining", "source": "auto",
  "trigger": { "kind": "http", "label": "GET /{campaignId}/remaining",
               "detail": { "verb": "GET", "path": "/{campaignId}/remaining" } } }
```

FastAPI 매핑 주의:
- 경로 prefix: `APIRouter(prefix=...)` + 데코레이터 경로를 합성해 full path 산출 (자바의 클래스 레벨 `@RequestMapping` 합성과 동일 과제, MVP에서 처리)
- verb: 데코레이터 메서드명(`get`/`post`/…) 대문자화. `@app.api_route(methods=[...])`는 메서드 목록에서 추출
- 라우트 데코레이터가 감싸도 노드 정의는 핸들러 함수 그대로, 데코레이터는 `auto.annotations`에도 기록
