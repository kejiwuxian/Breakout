/**
 * About — judge / enthusiast overview of Project Supernova.
 * Content mirrors root README.md without the full developer dump.
 */
import strings from "../copy/strings.json";

export function mountAbout(host: HTMLElement): void {
  host.innerHTML = `
    <article class="about-page" aria-labelledby="about-heading">
      <header class="about-hero">
        <p class="about-eyebrow">${strings.aboutEyebrow}</p>
        <h2 class="about-heading" id="about-heading">${strings.brand}</h2>
        <p class="about-tagline">${strings.aboutTagline}</p>
        <p class="about-lead">${strings.aboutLead}</p>
      </header>

      <section class="about-section" aria-labelledby="about-does">
        <h3 id="about-does">${strings.aboutDoesTitle}</h3>
        <ol class="about-steps">
          <li>${strings.aboutDoes1}</li>
          <li>${strings.aboutDoes2}</li>
          <li>${strings.aboutDoes3}</li>
        </ol>
        <p class="about-note">${strings.aboutHonesty}</p>
      </section>

      <section class="about-section" aria-labelledby="about-why">
        <h3 id="about-why">${strings.aboutWhyTitle}</h3>
        <p>${strings.aboutWhyBody}</p>
      </section>

      <section class="about-section" aria-labelledby="about-demo">
        <h3 id="about-demo">${strings.aboutDemoTitle}</h3>
        <ol class="about-steps">
          <li><strong>${strings.aboutDemo1Label}</strong> — ${strings.aboutDemo1}</li>
          <li><strong>${strings.aboutDemo2Label}</strong> — ${strings.aboutDemo2}</li>
          <li><strong>${strings.aboutDemo3Label}</strong> — ${strings.aboutDemo3}</li>
          <li><strong>${strings.aboutDemo4Label}</strong> — ${strings.aboutDemo4}</li>
          <li><strong>${strings.aboutDemo5Label}</strong> — ${strings.aboutDemo5}</li>
        </ol>
      </section>

      <section class="about-section about-tracks" aria-labelledby="about-tracks">
        <h3 id="about-tracks">${strings.aboutTracksTitle}</h3>
        <div class="about-track-grid">
          <div class="about-track">
            <h4>${strings.aboutCalHacksTitle}</h4>
            <p>${strings.aboutCalHacksBody}</p>
          </div>
          <div class="about-track">
            <h4>${strings.aboutSpaceXTitle}</h4>
            <p>${strings.aboutSpaceXBody}</p>
          </div>
        </div>
      </section>

      <section class="about-section" aria-labelledby="about-inside">
        <h3 id="about-inside">${strings.aboutInsideTitle}</h3>
        <ul class="about-inside">
          <li><strong>${strings.aboutInsideSkyLabel}</strong> — ${strings.aboutInsideSky}</li>
          <li><strong>${strings.aboutInsideRankLabel}</strong> — ${strings.aboutInsideRank}</li>
          <li><strong>${strings.aboutInsideSubLabel}</strong> — ${strings.aboutInsideSub}</li>
          <li><strong>${strings.aboutInsideReplayLabel}</strong> — ${strings.aboutInsideReplay}</li>
          <li><strong>${strings.aboutInsideVoiceLabel}</strong> — ${strings.aboutInsideVoice}</li>
        </ul>
      </section>

      <footer class="about-footer">
        <p>${strings.aboutDevLink}</p>
        <div class="about-actions">
          <a class="primary-btn about-back" href="#/" data-role="about-back">${strings.aboutBack}</a>
        </div>
      </footer>
    </article>
  `;
}
