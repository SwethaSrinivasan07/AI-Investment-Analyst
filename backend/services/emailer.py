"""
Email delivery service using SendGrid.
Sends formatted investment memos via email.
"""

import logging
import re
import textwrap

from models.database import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def memo_to_html(
    ticker: str,
    company: str,
    recommendation: str,
    conviction: str,
    markdown_text: str,
    memo_id: str,
    frontend_url: str,
) -> str:
    """Build the full HTML email body with inline styles."""

    # Recommendation badge colour
    badge_colors = {
        "Buy": "#16a34a",    # green-600
        "Pass": "#dc2626",   # red-600
        "Watch": "#d97706",  # amber-600
    }
    badge_bg = badge_colors.get(recommendation, "#6b7280")

    # Conviction badge colour
    conviction_colors = {
        "High": "#7c3aed",    # violet-700
        "Medium": "#0284c7",  # sky-600
        "Low": "#64748b",     # slate-500
    }
    conviction_bg = conviction_colors.get(conviction, "#64748b")

    # Build a plain-text preview from the first ~500 chars of the markdown.
    # Strip markdown syntax characters to keep it readable in an email preview.
    preview_raw = markdown_text[:600]
    preview_plain = re.sub(r"[#*_`>\[\]|]", "", preview_raw)
    preview_plain = re.sub(r"\n{2,}", "\n", preview_plain).strip()
    # Truncate cleanly at a word boundary ~500 chars
    if len(preview_plain) > 500:
        preview_plain = textwrap.shorten(preview_plain, width=500, placeholder=" …")

    memo_url = f"{frontend_url}/memo/{memo_id}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>[AlphaLens] {ticker} — {recommendation} | {conviction} Conviction</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;color:#18181b;">

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#f4f4f5;padding:32px 16px;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background-color:#ffffff;
                      border-radius:12px;overflow:hidden;
                      box-shadow:0 4px 6px rgba(0,0,0,0.08);">

          <!-- ── Header ── -->
          <tr>
            <td style="background-color:#1a1a2e;padding:32px 36px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <span style="font-size:26px;font-weight:700;
                                 color:#ffffff;letter-spacing:-0.5px;">
                      AlphaLens
                    </span>
                    <span style="display:block;font-size:12px;color:#a1a1aa;
                                 margin-top:2px;letter-spacing:0.5px;">
                      AI INVESTMENT ANALYST
                    </span>
                  </td>
                </tr>
                <!-- Ticker + badges row -->
                <tr>
                  <td style="padding-top:20px;">
                    <span style="font-size:32px;font-weight:800;color:#ffffff;">
                      {ticker}
                    </span>
                    <span style="font-size:15px;color:#d4d4d8;margin-left:8px;">
                      {company}
                    </span>
                    <br/>
                    <span style="display:inline-block;margin-top:12px;
                                 background-color:{badge_bg};color:#ffffff;
                                 font-size:13px;font-weight:700;
                                 padding:4px 14px;border-radius:999px;
                                 letter-spacing:0.5px;">
                      {recommendation.upper()}
                    </span>
                    <span style="display:inline-block;margin-left:8px;
                                 background-color:{conviction_bg};color:#ffffff;
                                 font-size:13px;font-weight:600;
                                 padding:4px 14px;border-radius:999px;
                                 letter-spacing:0.3px;">
                      {conviction} Conviction
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── Body ── -->
          <tr>
            <td style="padding:32px 36px;">

              <p style="margin:0 0 8px 0;font-size:13px;font-weight:600;
                        color:#71717a;text-transform:uppercase;letter-spacing:0.8px;">
                Memo Preview
              </p>

              <p style="margin:0 0 28px 0;font-size:15px;line-height:1.7;
                        color:#3f3f46;white-space:pre-line;">
                {preview_plain}
              </p>

              <!-- CTA button -->
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="background-color:#1a1a2e;border-radius:8px;">
                    <a href="{memo_url}"
                       style="display:inline-block;padding:14px 32px;
                              font-size:15px;font-weight:600;
                              color:#ffffff;text-decoration:none;
                              letter-spacing:0.2px;">
                      View Full Memo &rarr;
                    </a>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- ── Divider ── -->
          <tr>
            <td style="padding:0 36px;">
              <hr style="border:none;border-top:1px solid #e4e4e7;margin:0;" />
            </td>
          </tr>

          <!-- ── Footer ── -->
          <tr>
            <td style="padding:20px 36px 28px 36px;text-align:center;">
              <p style="margin:0;font-size:12px;color:#a1a1aa;line-height:1.6;">
                <strong style="color:#71717a;">AlphaLens</strong>
                &nbsp;&middot;&nbsp;
                For educational purposes only
                &nbsp;&middot;&nbsp;
                <em>Not financial advice</em>
              </p>
              <p style="margin:6px 0 0 0;font-size:11px;color:#d4d4d8;">
                You are receiving this because you have a scheduled memo set up in AlphaLens.
              </p>
            </td>
          </tr>

        </table>
        <!-- /Card -->

      </td>
    </tr>
  </table>
  <!-- /Outer wrapper -->

</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Public send function
# ---------------------------------------------------------------------------

async def send_memo_email(
    to_email: str,
    memo_ticker: str,
    memo_company: str,
    memo_recommendation: str,
    memo_conviction: str,
    memo_markdown: str,
    memo_id: str,
) -> bool:
    """
    Send an investment memo as an HTML email via SendGrid.

    Returns True on success, False on failure (never raises — errors are
    logged instead so a failed email never crashes the scheduler).
    """
    if not settings.sendgrid_api_key:
        logger.warning(
            "SENDGRID_API_KEY is not configured — skipping email to %s", to_email
        )
        return False

    try:
        import sendgrid as sg_module
        from sendgrid.helpers.mail import Mail, Email, To, Content

        subject = (
            f"[AlphaLens] {memo_ticker} — {memo_recommendation} "
            f"| {memo_conviction} Conviction"
        )

        html_body = memo_to_html(
            ticker=memo_ticker,
            company=memo_company,
            recommendation=memo_recommendation,
            conviction=memo_conviction,
            markdown_text=memo_markdown,
            memo_id=memo_id,
            frontend_url=settings.frontend_url,
        )

        message = Mail(
            from_email=Email("noreply@alphalens.ai", "AlphaLens"),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_body),
        )

        sg = sg_module.SendGridAPIClient(api_key=settings.sendgrid_api_key)
        # SendGrid client is synchronous; run it in a thread to avoid blocking
        import asyncio
        response = await asyncio.to_thread(sg.send, message)

        if 200 <= response.status_code < 300:
            logger.info(
                "Memo email sent to %s for %s (memo_id=%s, status=%s)",
                to_email,
                memo_ticker,
                memo_id,
                response.status_code,
            )
            return True
        else:
            logger.error(
                "SendGrid returned non-2xx status %s for %s",
                response.status_code,
                to_email,
            )
            return False

    except Exception as exc:
        logger.error(
            "Failed to send memo email to %s: %s",
            to_email,
            exc,
            exc_info=True,
        )
        return False
