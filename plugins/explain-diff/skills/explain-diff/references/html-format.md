# HTML 형식과 점검 목록

`SKILL.md`의 5절에서 HTML을 쓸 때 읽습니다.

## 뼈대

- `<meta name="viewport" content="width=device-width, initial-scale=1">`를 넣습니다. 휴대폰에서도 읽기 좋게 합니다.
- 맨 위에 제목, 대상(PR 번호·브랜치·커밋 범위), 만든 날짜를 둡니다.
- 목차는 앵커 링크 목록입니다. 섹션 네 개는 `<h2 id="...">`로 둡니다.
- 넓은 배경은 `<details><summary>처음이라면: …</summary>…</details>`로 접어 둡니다.
- 본문 폭은 760px 안팎으로 묶습니다. 표·그림·코드 블록이 좁은 화면에서 페이지 전체를 가로로 밀지 않게
  `overflow-x: auto`를 줍니다.
- 색은 `:root`의 CSS 변수로 정하고 `@media (prefers-color-scheme: dark)`에서 다시 정합니다.

## 코드 블록

- 코드는 항상 `<pre><code>…</code></pre>`에 넣습니다. 다른 요소를 쓴다면 CSS에 `white-space: pre` 또는
  `pre-wrap`이 반드시 있어야 합니다. 없으면 브라우저가 줄바꿈을 모두 한 줄로 합칩니다.
- `<`, `>`, `&`는 `&lt;`, `&gt;`, `&amp;`로 바꿉니다.
- diff를 보여 줄 때는 추가·삭제 줄에 색을 주되, 색만으로 구분하지 않도록 줄 앞의 `+`·`-`를 남깁니다.

## callout

종류를 2~3가지로 정해 되풀이합니다(예: 개념, 주의, 경계 사례). 각각 `role="note"`와 앞머리 낱말
("개념", "주의")을 둬서 색을 보지 못해도 구분되게 합니다.

## 그림

- CSS grid·flex 상자와 화살표(`→` 문자나 테두리)로 그립니다. 예시 데이터는 `<code>`로 넣습니다.
- 한 그림 종류는 페이지 안에서 같은 모양과 색을 씁니다. 처음 나올 때 범례를 한 줄 둡니다.

## 퀴즈 골격

보기는 `<button>`으로 만들어 키보드로도 고를 수 있게 합니다. 다시 고를 수 있습니다.

```html
<div class="quiz" data-answer="2">
  <p class="question">1. 질문</p>
  <button type="button" class="option" data-why="왜 틀렸는지">보기 1</button>
  <button type="button" class="option" data-why="왜 맞는지">보기 2</button>
  <button type="button" class="option" data-why="왜 틀렸는지">보기 3</button>
  <button type="button" class="option" data-why="왜 틀렸는지">보기 4</button>
  <p class="feedback" aria-live="polite"></p>
</div>

<script>
  document.querySelectorAll(".quiz").forEach((quiz) => {
    const answer = Number(quiz.dataset.answer);
    const options = [...quiz.querySelectorAll(".option")];
    const feedback = quiz.querySelector(".feedback");

    options.forEach((option, index) => {
      option.addEventListener("click", () => {
        const correct = index + 1 === answer;
        options.forEach((o) => o.classList.remove("right", "wrong"));
        option.classList.add(correct ? "right" : "wrong");
        feedback.textContent = (correct ? "맞습니다. " : "아닙니다. ") + option.dataset.why;
      });
    });
  });
</script>
```

`맞습니다`·`아닙니다`는 페이지 언어에 맞춰 바꿉니다. 정답 위치는 문항마다 다르게 둡니다.

## 저장 전 점검 목록

- [ ] 섹션 네 개가 배경 → 직관 → 코드 → 퀴즈 순서이고, 목차 링크가 모두 해당 섹션으로 이동한다
- [ ] 퀴즈가 5문항이고, 문항마다 정답이 정확히 하나이며, 모든 보기에 `data-why`가 있다
- [ ] 모든 코드 블록이 `<pre>`이거나 `white-space: pre`/`pre-wrap`을 가진다. HTML 소스에서 하나씩 확인한다
- [ ] 외부 리소스를 불러오지 않는다(`src`나 `<link href>`가 `http(s)://`로 시작하지 않는다. 본문의 참고 링크는 괜찮다)
- [ ] ASCII 그림이 없다
- [ ] 비밀값이 없다
- [ ] 파일명이 오늘 날짜 `YYYY-MM-DD-`로 시작하고, 저장 위치가 저장소 밖이다
