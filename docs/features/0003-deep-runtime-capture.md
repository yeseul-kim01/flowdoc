# 0003 — 런타임 심층 캡처 (SQL · 외부호출 · 성능, 그리고 N+1 분석)

- **상태**: 🔄 계획 (추후 개발)
- **로드맵**: v0.3+ (0001 런타임 오버레이를 깊게 확장). 기획안 §9 스펙 확장 + §10 트레이스 뷰.
- **백로그**: ideas.md C4 N+1(🔬), B1 트랜잭션 위험(✅), D1 외부 의존 맵(✅) — 정적 근사로만 있던 것들을 **런타임 실측**으로 끌어올림.
- **브랜치**: `feat/deep-runtime-capture` (미정)
- **담당**: 수집기 양쪽(kys/jch) + 공유 스펙/UI(양측 합의)
- **선행 의존**: [[0001-runtime-trace-overlay]] (span 위에 부가 데이터를 붙이는 구조). [[0002-sequence-lens]]와 보완 관계.

## 무엇을 / 왜

0001의 런타임 트레이스는 **구조·순서·tx 경계·실패 위치**까지 본다(가벼운 altitude). 하지만 협업·리뷰·
디버깅에서 자주 필요한 다음은 못 본다:

- "이 호출이 **실제로 어떤 SQL을, 몇 번** 쐈나?" → 루프 안 반복 쿼리(**N+1**)
- "이 구간이 **얼마나 느렸나**, 시간이 어디서 샜나?" → self-time / 느린 span
- "런타임에 **외부로 뭘 불렀나**(HTTP/Redis/Mongo)?" → 외부 의존 **실측**(정적 경계 노드의 사후 검증)

이건 정적 분석으로는 근사만 가능하다(예: "루프 안 repository 호출" 패턴 매칭). **런타임이면 실측**이 된다 —
실제로 발생한 쿼리 수·시간을 그대로 보여줄 수 있다. 0003은 각 span에 **실측 부가 데이터**(쿼리·외부호출·
타이밍, 선택적 인자/리턴)를 붙이고, 그 위에 **N+1·성능·외부의존 분석 렌즈**를 얹는다.

### 비-목표 / altitude 가드 (우리 색깔 유지)
"전부 깊게 녹화"로 가면 정체성(구조 + 선언된 의도)이 흐려진다. 그래서:
- **기본은 메타데이터** — SQL **정규화 텍스트**·횟수·시간 (리터럴 값 제거). 실제 파라미터 값·페이로드·
  리턴 값은 **기본 수집 안 함**, opt-in + 마스킹일 때만.
- 심층 데이터는 **분석 렌즈로 분리** — 기본 트레이스 뷰는 지금처럼 깔끔하게 둔다.
- "더 깊은 녹화" 자체가 목적이 아니라, **협업 관심사(N+1·핫스팟·외부 결합)를 실측으로 검증**하는 게 목적.

## 스펙 영향 (⚠ shared contract — 큰 확장)

`Span`에 **옵션 부가 필드** 추가 (모두 nullable, 미수집 시 생략):

```
span += {
  queries?:  [ { sql, count, totalMs, rows? } ],   // sql = 정규화된 텍스트(리터럴→?)
  external?: [ { kind, target, count, totalMs } ],  // kind: "http"|"redis"|"mongo"|...
  selfMs?:   number,                                 // 자기 시간 = 총시간 - 자식 합
  args?:     [ { name, value } ],                    // opt-in + 마스킹
  returns?:  { value }                               // opt-in + 마스킹
}
```

`Trace` 또는 신규 최상위에 **파생 분석** (수집 데이터에서 계산):
```
analyses?: [ { kind: "n+1"|"slow"|"ext-heavy", nodeId, spanId, detail, severity } ]
```

- 명백한 스키마 확장 → **양측 합의 + 양쪽 동시 반영** (collaboration.md). parity 이슈에 `spec` 라벨.
- altitude 결정: `queries[].sql`은 **정규화 필수**(리터럴/`IN (...)` → `?`) — N+1 그룹핑 키이자 PII 제거 수단.
- `args`/`returns`는 스키마엔 있되 **수집은 기본 OFF**(아래 보안 참고).

## 아키텍처 + 기술 난제

핵심 메커니즘: **"지금 실행 중인 span"에 부가 이벤트를 귀속**시킨다. 0001의 `TraceRecorder`는 이미 스레드별
span 스택을 들고 있으므로, 각 캡처 인터셉터가 `recorder.currentSpan()`에 데이터를 attach.

**캡처 소스 (Spring)**
- **SQL**: `DataSource` 프록시(datasource-proxy / p6spy) 또는 Hibernate `StatementInspector`로 쿼리·시간·rows를
  가로채 현재 span에 attach + **정규화**.
- **외부 HTTP**: `RestTemplate`/`RestClient` 인터셉터, `WebClient` 필터, OpenFeign.
- **Redis/Mongo 등**: Spring Data 콜백 또는 **Micrometer Observation**(이미 표준 훅) 구독.
- **인자/리턴**: 0001 애스펙트의 `ProceedingJoinPoint.getArgs()`/반환값에서 — **opt-in**일 때만, 마스킹 통과 후.

**파생 분석**
- **N+1**: 한 부모 span 아래 **같은 정규화 SQL**이 임계치(예 ≥ N회) 이상 반복 → finding. 런타임 실측이라
  정적 패턴 매칭보다 정확(실제 횟수 제시).
- **성능/핫스팟**: `selfMs = span.total - Σ child.total`. self-time 랭킹 + 경량 플레임(트리+시간을 UI가 렌더).
- **외부 과다**: 한 흐름이 외부 경계를 임계 이상 호출 → finding(D1 실측판).

**진짜 난제**
1. **PII / 보안 (최우선).** 값·SQL 리터럴은 민감 정보일 수 있다.
   - 기본값: **수집 안 함**. SQL은 **정규화**로 리터럴 제거. `args`/`returns`는 opt-in.
   - 마스킹: `@FlowMask` 어노테이션·필드명 규칙(`password`,`token`,`ssn`…)·타입 기반 truncation.
   - 노출 가드: 심층 데이터 서빙은 **프로파일/프로퍼티로 제한**(`flowdoc.capture.* = false` 기본, prod 차단).
   - 정직성: UI는 "이 환경에선 심층 캡처 OFF"를 명시(빈 값을 "없음"으로 오해 안 하게).
2. **오버헤드.** DataSource 프록시·인자 캡처는 비용. **샘플링**(요청 N건당 1), 버퍼 상한, prod 가드. 기본은
   로컬/테스트 프로파일에서만 권장.
3. **current-span 정합.** 비동기/커넥션 풀에서 그 SQL이 **어느 span에 속하는지**. 0001 Phase 2 스레드홉
   전파에 의존. 풀 스레드에서 컨텍스트 전파 안 되면 그 쿼리는 "귀속 불명"으로 정직 표기.
4. **SQL 정규화.** 리터럴·`IN (...)`·주석 제거로 안정적 그룹핑 키 생성(+PII 제거). 방언 차이 고려.
5. **관측 밖과의 일관성.** repository는 트리에서 "관측 밖"(자체 span 없음)인데 SQL은 그 안에서 난다.
   → SQL을 **가장 가까운 관측 span**(예: `CouponService.issue`)에 귀속하고 "이 프레임이 쏜 쿼리"로 표기.
   관측 밖 경계를 "쿼리는 보이는데 호출 프레임은 못 본다"고 정직하게 설명.
6. **altitude 유지.** 기본 트레이스 뷰는 깔끔히, 심층은 **별도 렌즈/패널**(span 펼침의 "런타임 실측" 섹션).

## 단계 분할

- **Phase 1 — SQL 메타데이터:** DataSource 프록시로 쿼리 **정규화 텍스트·횟수·시간**을 현재 span에 귀속.
  span 펼침에 "쿼리 N건 · Xms" 표시. **값/페이로드 없음 → PII 안전.** (스키마: `span.queries[]`)
- **Phase 2 — N+1 & 성능 렌즈:** 같은 정규화 SQL 반복 임계 → N+1 finding. `selfMs` 계산 + 느린 span 랭킹/
  경량 플레임. (스키마: `analyses[]`, `span.selfMs`)
- **Phase 3 — 외부 호출 실측:** HTTP/Redis/Mongo 캡처 → `span.external[]`. D1 외부 의존 맵을 실측으로 보강.
- **Phase 4 — 인자/리턴 (가장 민감, 기본 OFF):** opt-in + `@FlowMask`·필드 redaction·프로파일 가드.
  (스키마: `span.args[]`, `span.returns`)

## 패리티 (Spring ↔ FastAPI)

같은 부가 필드를 양쪽이 산출. kys 선행 → parity 이슈(`spec` 라벨) → jch 미러.

| 캡처 | Spring (kys) | FastAPI (jch) |
|---|---|---|
| SQL | DataSource 프록시 / Hibernate StatementInspector | SQLAlchemy `before/after_cursor_execute` 이벤트 |
| 외부 HTTP | RestClient/WebClient 인터셉터 | httpx/requests 인스트루먼트 |
| current-span 귀속 | ThreadLocal span 스택 | contextvars 현재 span |
| 정규화·마스킹 | 공용 규칙(동일 결과) | 공용 규칙(동일 결과) |
| 서빙 | 동일 `/flowdoc/traces.json`에 부가 필드 | 동일 |

> 정규화·마스킹 규칙은 **양쪽이 같은 결과**를 내야 패리티(같은 SQL → 같은 정규화 키). 규칙 문서를 공유.

## 완료 기준

- coupon-rush에 **의도적 N+1**(루프 안 조회)을 심어 → 분석 렌즈가 "같은 쿼리 ×N"으로 **실측 탐지**.
- span별 **쿼리 수·시간**, 흐름별 **self-time 핫스팟**, **외부 호출 실측**이 표시됨.
- **PII 기본 미수집** 확인 — SQL 정규화로 리터럴 없음, `args`/`returns` OFF 기본, 캡처 OFF 시 UI가 명시.
- 예제 `flowdoc.json`(부가 필드 포함)이 `spec/flowdoc-0.1.schema.json` 통과.
- 같은 `ui/index.html`에서 **Java·Python 동일**하게 렌더.
