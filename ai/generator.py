import os
import json
import logging
import threading
import queue
from typing import Dict, Any, List, Optional

# Import the OpenAI client
from openai import OpenAI
# Import error types for exception handling
try:
    from openai import APITimeoutError, APIConnectionError, RateLimitError
except ImportError:
    # Define fallback error classes if imports fail
    class APITimeoutError(Exception): pass
    class APIConnectionError(Exception): pass
    class RateLimitError(Exception): pass

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize OpenAI client with safeguards
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("OpenAI API key not found in environment variables. AI features will be limited.")
    openai = None
else:
    try:
        openai = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing OpenAI client: {str(e)}")
        openai = None

def generate_case_study(document_data: Dict[str, Any], audience: str = "general") -> Dict[str, Any]:
    """
    Generate a case study from the extracted document data

    Args:
        document_data: Dictionary containing the extracted text and images
        audience: Target audience for the case study

    Returns:
        Dictionary containing the generated case study
    """
    logger.debug("Generating case study")

    # Safety check: ensure we have complete document data
    if not document_data or not isinstance(document_data, dict):
        logger.error("Invalid document data received for case study generation")
        return _generate_fallback_case_study({}, audience)

    # If the document is flagged to skip AI processing (large PPTX files), use fallback immediately
    if document_data.get('skip_ai_processing', False):
        logger.info("Document flagged to skip AI processing. Using fallback generation.")
        return _generate_fallback_case_study(document_data, audience)

    # Extremely large files should use fallback immediately
    file_size_check = document_data.get('file_size', 0)
    if file_size_check and file_size_check > 100 * 1024 * 1024:  # > 100MB
        logger.debug(f"Very large file detected ({file_size_check/1024/1024:.1f}MB). Using fallback generation.")
        return _generate_fallback_case_study(document_data, audience)

    extracted_text = document_data.get('text', '')
    images = document_data.get('images', [])
    structured_content = document_data.get('structured_content', {})

    # Check for missing content
    if not extracted_text:
        logger.warning("No extracted text found in document data. Using fallback generator.")
        return _generate_fallback_case_study(document_data, audience)

    # Check for extra large text input
    original_text_length = len(extracted_text)

    # If the input is extremely large, use fallback immediately
    if original_text_length > 200000:  # 200K characters
        logger.warning(f"Extremely large text input detected ({original_text_length} chars). Using fallback generator.")
        return _generate_fallback_case_study(document_data, audience)

    is_large_input = original_text_length > 20000  # OpenAI has token limits

    if is_large_input:
        logger.debug(f"Large text input detected ({original_text_length} chars). Truncating for AI processing")

        # Instead of sending all text, use a strategic truncation approach
        sections = structured_content.get('sections', [])

        if sections and len(sections) > 5:
            # Use structured content sections if available
            # Keep first sections, some from middle, and some from end
            keep_sections = []

            # Keep up to 5 first sections
            keep_sections.extend(sections[:5])

            # Keep a few from the middle if there are many sections
            if len(sections) > 15:
                middle_start = len(sections) // 3
                keep_sections.extend(sections[middle_start:middle_start+3])

            # Keep up to 5 last sections
            keep_sections.extend(sections[-5:])

            # Combine into a single text with section headers
            compact_text = ""
            for section in keep_sections:
                title = section.get('title', '')
                content = section.get('content', '')
                if title and content:
                    snippet = content[:600]  # Limit each section size even more
                    compact_text += f"\n## {title}\n{snippet}\n"

            # Only truncate if we successfully built a compact representation
            if len(compact_text) > 1000:
                extracted_text = compact_text
                logger.debug(f"Using structured compact text ({len(compact_text)} chars)")
        else:
            # More aggressive truncation strategy: first 10K chars + last 5K
            first_part = extracted_text[:10000]

            # Add a smaller snippet from the middle only for moderately large texts
            if original_text_length < 100000:
                middle_start = len(extracted_text) // 2 - 1000
                middle_part = extracted_text[middle_start:middle_start+2000]
                last_part = extracted_text[-5000:]
                extracted_text = first_part + "\n\n[...content truncated...]\n\n" + middle_part + "\n\n[...content truncated...]\n\n" + last_part
            else:
                # For very large texts, just use beginning and end
                last_part = extracted_text[-5000:]
                extracted_text = first_part + "\n\n[...most content truncated...]\n\n" + last_part

            logger.debug(f"Truncated text from {original_text_length} to {len(extracted_text)} chars")

    # Check for OpenAI availability, with exponential backoff in case of initialization issues
    if openai is None:
        logger.warning("OpenAI not available. Using basic extraction for case study generation.")
        return _generate_fallback_case_study(document_data, audience)

    # Try to use OpenAI first, with fallback mechanism
    try:
        # Start a separate thread with a timeout for OpenAI generation

        result_queue = queue.Queue()

        def openai_generation():
            try:
                # Create the case study using OpenAI
                ai_result = _generate_with_openai(extracted_text, audience, is_large_input)
                if ai_result:
                    # Add images to the case study
                    selected_images = select_key_images(images, ai_result, max_images=3)
                    ai_result['images'] = selected_images
                    result_queue.put(("success", ai_result))
                else:
                    result_queue.put(("error", None))
            except Exception as e:
                logger.error(f"Error in OpenAI generation thread: {str(e)}")
                result_queue.put(("error", str(e)))

        # Start the generation thread
        generation_thread = threading.Thread(target=openai_generation)
        generation_thread.daemon = True
        generation_thread.start()

        # Wait for the result with a timeout (more time for large inputs)
        timeout_seconds = 60 if is_large_input else 30
        generation_thread.join(timeout_seconds)

        if generation_thread.is_alive():
            # If the thread is still running after timeout, use fallback
            logger.warning(f"OpenAI generation thread timed out after {timeout_seconds}s. Using fallback generator.")
            return _generate_fallback_case_study(document_data, audience)

        # Check if we have a result
        try:
            status, result = result_queue.get_nowait()
            if status == "success" and result:
                return result
            else:
                logger.warning(f"OpenAI generation failed with status: {status}. Using fallback generator.")
                return _generate_fallback_case_study(document_data, audience)
        except queue.Empty:
            logger.warning("No result from OpenAI generation thread. Using fallback generator.")
            return _generate_fallback_case_study(document_data, audience)

    except Exception as e:
        logger.error(f"Error in OpenAI case study generation: {str(e)}")
        # Use fallback mechanism
        return _generate_fallback_case_study(document_data, audience)

    # If OpenAI is available, use it to generate a case study
    # Create a prompt for OpenAI
    audience_prompt = f"Target audience: {audience}. " if audience != "general" else ""

    prompt = f"""
    Based on the following content, generate a professional case study with these sections:
    1. Challenge: Describe the key problems or challenges faced
    2. Approach: How the challenge was addressed
    3. Solution: The implemented solution
    4. Outcomes: Results and benefits achieved

    {audience_prompt}
    Extract the most relevant information to construct a compelling narrative.
    Return the response as JSON in the following format:
    {{
        "title": "Title of the case study",
        "challenge": "Challenge section content",
        "approach": "Approach section content",
        "solution": "Solution section content",
        "outcomes": "Outcomes section content",
        "summary": "A brief executive summary",
        "key_points": ["Point 1", "Point 2", "Point 3"],
    }}

    The content should be:
    1. Well-structured and professional
    2. Between 300-500 words total
    3. Based exclusively on the information provided

    Here is the extracted text:
    {extracted_text}
    """

    # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
    # do not change this unless explicitly requested by the user
    retry_count = 0
    max_retries = 3

    while retry_count < max_retries:
        try:
            logger.debug(f"Calling OpenAI API (attempt {retry_count + 1})")

            # Set a longer timeout for large documents
            import httpx
            from openai import APITimeoutError, APIConnectionError, RateLimitError

            # Use a longer timeout for large inputs
            timeout_seconds = 60.0 if is_large_input else 30.0
            client = httpx.Client(timeout=timeout_seconds)

            # Calculate max tokens based on the prompt length
            prompt_length = len(prompt)
            logger.debug(f"Prompt length: {prompt_length} characters")

            # Adjust max_tokens for output based on input size to avoid token limit errors
            max_output_tokens = 3000 if prompt_length < 30000 else 2000

            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a professional case study writer who creates compelling business narratives."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=max_output_tokens,
                timeout=timeout_seconds
            )

            logger.debug("Successfully received OpenAI response")
            case_study_content = json.loads(response.choices[0].message.content)

            # Select key images (up to 3)
            selected_images = select_key_images(images, case_study_content, max_images=3)
            break  # Success - exit retry loop

        except (APITimeoutError, APIConnectionError) as e:
            logger.error(f"OpenAI API timeout or connection error (attempt {retry_count + 1}): {str(e)}")
            retry_count += 1

            # For large inputs, be more aggressive with truncation on retry
            if is_large_input and retry_count < max_retries:
                logger.debug("Reducing input size for retry with large document")
                # Further reduce input size for next attempt
                truncation_factor = 0.7 - (0.1 * retry_count)  # 0.6, 0.5 for subsequent retries
                extracted_text_length = len(extracted_text)
                new_length = int(extracted_text_length * truncation_factor)

                # Keep first half and last quarter of the truncated text
                first_part_ratio = 0.75
                first_part_size = int(new_length * first_part_ratio)
                last_part_size = new_length - first_part_size

                new_text = extracted_text[:first_part_size] + "\n\n[...content significantly truncated...]\n\n" + extracted_text[-last_part_size:]
                logger.debug(f"Truncated text from {extracted_text_length} to {len(new_text)} chars for retry {retry_count}")

                # Create new prompt with truncated text
                prompt = prompt.replace(extracted_text, new_text)
                extracted_text = new_text

            if retry_count >= max_retries:
                logger.error("Max retries reached for OpenAI API call, using fallback")
                # Use fallback method
                return _generate_fallback_case_study(document_data, audience)

            # Wait with exponential backoff between retries
            import time
            time.sleep(2 ** retry_count)  # 2, 4, 8 seconds

        except RateLimitError as e:
            logger.error(f"OpenAI API rate limit exceeded: {str(e)}")
            # Don't retry on rate limit errors, use fallback immediately
            return _generate_fallback_case_study(document_data, audience)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error calling OpenAI API: {error_msg}")

            # Check for token limit errors
            if "maximum context length" in error_msg or "token limit" in error_msg:
                logger.debug("Token limit exceeded, truncating input")

                # Aggressive truncation on token limit errors
                current_length = len(extracted_text)
                # Keep just 25% of the original size
                new_length = current_length // 4

                # Distribute between start and end, with more focus on the start
                start_portion = int(new_length * 0.75)
                end_portion = new_length - start_portion

                new_text = extracted_text[:start_portion] + "\n\n[...most content removed due to token limits...]\n\n" + extracted_text[-end_portion:]
                logger.debug(f"Aggressively truncated text from {current_length} to {len(new_text)} chars due to token limits")

                # Replace text in prompt
                prompt = prompt.replace(extracted_text, new_text)
                extracted_text = new_text

            retry_count += 1

            if retry_count >= max_retries:
                logger.error("Max retries reached after errors, using fallback")
                return _generate_fallback_case_study(document_data, audience)

            # Wait between retries
            import time
            time.sleep(2 * retry_count)

    # Add images to the case study and return the result
    case_study_content['images'] = selected_images
    return case_study_content

# Helper function for OpenAI-based generation
def _generate_with_openai(extracted_text: str, audience: str = "general", is_large_input: bool = False) -> Optional[Dict[str, Any]]:
    """
    Generate a case study using OpenAI

    Args:
        extracted_text: The extracted text content
        audience: Target audience for the case study
        is_large_input: Whether the input is considered large

    Returns:
        Dictionary containing the generated case study or None if failed
    """
    logger.debug("Generating case study with OpenAI")

    if openai is None:
        logger.warning("OpenAI client not initialized")
        return None

    # Create a prompt for OpenAI
    audience_prompt = f"Target audience: {audience}. " if audience != "general" else ""

    # Simplified prompt for large inputs
    if is_large_input:
        prompt = f"""
        Extract key information from this content to create a concise professional case study.
        Include these sections:
        1. Challenge: The key problems or challenges faced
        2. Approach: How the challenge was addressed
        3. Solution: The implemented solution
        4. Outcomes: Results and benefits achieved

        {audience_prompt}
        Return ONLY JSON in this format:
        {{
            "title": "Title of the case study",
            "challenge": "Challenge section content",
            "approach": "Approach section content",
            "solution": "Solution section content",
            "outcomes": "Outcomes section content",
            "summary": "A brief executive summary",
            "key_points": ["Point 1", "Point 2", "Point 3"]
        }}

        Keep it concise (300-400 words total).

        Here is the content:
        {extracted_text}
        """
    else:
        prompt = f"""
        Based on the following content, generate a professional case study with these sections:
        1. Challenge: Describe the key problems or challenges faced
        2. Approach: How the challenge was addressed
        3. Solution: The implemented solution
        4. Outcomes: Results and benefits achieved

        {audience_prompt}
        Extract the most relevant information to construct a compelling narrative.
        Return the response as JSON in the following format:
        {{
            "title": "Title of the case study",
            "challenge": "Challenge section content",
            "approach": "Approach section content",
            "solution": "Solution section content",
            "outcomes": "Outcomes section content",
            "summary": "A brief executive summary",
            "key_points": ["Point 1", "Point 2", "Point 3"]
        }}

        The content should be:
        1. Well-structured and professional
        2. Between 300-500 words total
        3. Based exclusively on the information provided

        Here is the extracted text:
        {extracted_text}
        """

    # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
    # do not change this unless explicitly requested by the user
    try:
        # Set a reasonable timeout

        # Use a longer timeout for large inputs
        timeout_seconds = 40.0 if is_large_input else 20.0

        # Calculate max tokens based on the prompt length
        prompt_length = len(prompt)
        logger.debug(f"Prompt length: {prompt_length} characters")

        # Adjust max_tokens for output based on input size to avoid token limit errors
        max_output_tokens = 2000 if prompt_length < 20000 else 1500

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a professional case study writer who creates compelling business narratives."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=max_output_tokens,
            timeout=timeout_seconds
        )

        logger.debug("Successfully received OpenAI response")
        try:
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse OpenAI response as JSON: {str(json_err)}")
            return None

    except Exception as e:
        logger.error(f"Error in OpenAI case study generation: {str(e)}")
        return None

# Helper function for fallback case study generation when OpenAI fails
def _generate_fallback_case_study(document_data: Dict[str, Any], audience: str = "general") -> Dict[str, Any]:
    """Generate a fallback case study when OpenAI is unavailable or fails"""
    logger.info("Using fallback case study generation")

    extracted_text = document_data.get('text', '')
    images = document_data.get('images', [])

    # Create a fallback case study with improved content extraction
    title = "Document Analysis Report"

    # Try to extract a better title from the structured content if available
    structured_content = document_data.get('structured_content', {})
    if structured_content and structured_content.get('title'):
        title = structured_content.get('title')

    # Determine the file type for better extraction logic
    file_type = document_data.get('file_type', '')
    is_pptx = file_type.lower() == 'pptx'

    # Get sections from structured content or extract content
    sections = structured_content.get('sections', [])
    key_points = structured_content.get('key_points', [])

    # Default content for sections
    challenge = "Analysis of the provided document content."
    approach = "Document processing and content extraction."
    solution = "Automated extraction of key information from the document."
    outcomes = "Generated report based on document analysis."
    summary = "This report was automatically generated from the document content."

    # PPTX-specific improved extraction
    if is_pptx:
        # Attempt to identify slide titles and use them to organize content
        slide_titles = []
        slide_content = {}
        current_title = None

        # Initialize these variables for later reference
        challenge_content = []
        approach_content = []
        solution_content = []
        outcomes_content = []

        # First pass: identify slide titles
        lines = extracted_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip footer text (often contains page numbers, dates, confidentiality notices)
            if any(footer_text in line.lower() for footer_text in 
                  ['confidential', 'page', 'copyright', '©', 'all rights reserved', 'footer']):
                continue

            # Check if this looks like a slide title (short, less than ~60 chars)
            if len(line) < 60 and not line.endswith('.'):
                # Check for title case or all caps as an indicator of a title
                words = line.split()
                if (len(words) <= 10 and 
                    (line.istitle() or line.isupper() or 
                     any(word[0].isupper() for word in words if word and len(word) > 1))):
                    slide_titles.append(line)
                    current_title = line
                    slide_content[current_title] = []
            elif current_title:
                # Add content to the current slide
                slide_content[current_title].append(line)

        # Now match slide content to case study sections based on likely topics
        challenge_keywords = ['challenge', 'problem', 'issue', 'background', 'overview', 'introduction']
        approach_keywords = ['approach', 'methodology', 'strategy', 'process', 'plan']
        solution_keywords = ['solution', 'implementation', 'platform', 'technology', 'product']
        outcomes_keywords = ['outcomes', 'results', 'benefits', 'impact', 'conclusion', 'success']

        for title, content in slide_content.items():
            lower_title = title.lower()
            # Compare with keywords
            if any(keyword in lower_title for keyword in challenge_keywords):
                challenge_content.extend(content)
            elif any(keyword in lower_title for keyword in approach_keywords):
                approach_content.extend(content)
            elif any(keyword in lower_title for keyword in solution_keywords):
                solution_content.extend(content)
            elif any(keyword in lower_title for keyword in outcomes_keywords):
                outcomes_content.extend(content)
            # Add to the most appropriate section based on position if no keyword match
            elif len(challenge_content) < 3:
                challenge_content.extend(content)
            elif len(approach_content) < 3:
                approach_content.extend(content)
            elif len(solution_content) < 3:
                solution_content.extend(content)
            else:
                outcomes_content.extend(content)

        # Create the content for each section
        if challenge_content:
            challenge = " ".join(challenge_content)[:800]
        if approach_content:
            approach = " ".join(approach_content)[:800]
        if solution_content:
            solution = " ".join(solution_content)[:800]
        if outcomes_content:
            outcomes = " ".join(outcomes_content)[:800]

        # Generate a summary from the first parts of each section
        summary_parts = []
        if challenge_content:
            summary_parts.append(" ".join(challenge_content[:2]))
        if solution_content:
            summary_parts.append(" ".join(solution_content[:2]))
        if summary_parts:
            summary = " ".join(summary_parts)[:400]

        # Generate key points
        all_key_points = []
        if slide_titles and len(slide_titles) > 3:
            # Use some slide titles as key points
            relevant_titles = [title for title in slide_titles 
                           if not any(common in title.lower() for common in 
                                    ['agenda', 'content', 'overview', 'thank'])][:5]
            all_key_points.extend(relevant_titles)

        # Add some content-based key points
        for content_list in [challenge_content, solution_content, outcomes_content]:
            if content_list:
                # Find sentences that might be bullet points or key statements
                for line in content_list:
                    if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                        all_key_points.append(line.lstrip('•-* '))

        # Use the first few meaningful key points
        if all_key_points:
            key_points = [kp for kp in all_key_points if len(kp) > 15 and len(kp) < 100][:5]

    # For non-PPTX files or if the above extraction didn't work well
    if not is_pptx or (is_pptx and not any([challenge_content, approach_content, solution_content, outcomes_content])):
        # Fall back to the original section-based extraction
        if sections:
            # Use the first few sections for different parts of the case study
            sections_content = [section.get('content', '') for section in sections if section.get('content')]

            if len(sections_content) >= 1:
                challenge = sections_content[0][:800]  # Limit length but allow more content
            if len(sections_content) >= 2:
                approach = sections_content[1][:800]
            if len(sections_content) >= 3:
                solution = sections_content[2][:800]
            if len(sections_content) >= 4:
                outcomes = sections_content[3][:800]

            # Create a summary from the first parts of each section
            summary_parts = [content[:150] for content in sections_content[:3]]
            summary = " ".join(summary_parts)

    # Select images - try to match images to sections
    selected_images = select_key_images(images, {
        "challenge": challenge,
        "approach": approach,
        "solution": solution,
        "outcomes": outcomes
    }, max_images=3)

    # Create the case study structure
    case_study_content = {
        "title": title,
        "challenge": challenge,
        "approach": approach,
        "solution": solution,
        "outcomes": outcomes,
        "summary": summary,
        "key_points": key_points if key_points else ["Document processed successfully", "Content extracted and analyzed", "Report generated from content"],
        "images": selected_images
    }

    return case_study_content

def select_key_images(images: List[Dict[str, Any]], case_study: Dict[str, Any], max_images: int = 3) -> List[Dict[str, Any]]:
    """
    Select key images for the case study

    Args:
        images: List of extracted images
        case_study: The generated case study content
        max_images: Maximum number of images to select

    Returns:
        List of selected images
    """
    if not images:
        return []

    # If there are only a few images, use all of them
    if len(images) <= max_images:
        return images

    # Get case study content as text for comparison
    case_study_text = ""
    if case_study:
        case_study_text = " ".join([
            case_study.get('title', ''),
            case_study.get('challenge', ''),
            case_study.get('approach', ''),
            case_study.get('solution', ''),
            case_study.get('outcomes', ''),
            case_study.get('summary', '')
        ]).lower()

    # Score and rank images
    scored_images = []

    for i, img in enumerate(images):
        score = 0
        caption = img.get('caption', '').lower()

        # Base score based on position (earlier images often more important)
        position_score = max(0, 100 - i)  # Earlier position is better
        score += position_score * 0.5

        # Boost score if it's from first few pages/slides
        if "slide 1" in caption or "page 1" in caption or "cover" in caption:
            score += 100
        elif "slide 2" in caption or "page 2" in caption:
            score += 80
        elif any(f"slide {n}" in caption for n in range(3, 6)) or any(f"page {n}" in caption for n in range(3, 6)):
            score += 60

        # Check if caption contains words from the case study (relevance)
        if case_study_text and caption:
            # Add points for each meaningful word in caption that's also in case study
            meaningful_words = [word for word in caption.split() if len(word) > 4]
            for word in meaningful_words:
                if word in case_study_text:
                    score += 10

        # Check for likely diagrams, charts, or infographics which are valuable
        if any(keyword in caption.lower() for keyword in ['diagram', 'chart', 'graph', 'figure', 'process', 'workflow', 'infographic', 'results']):
            score += 50

        # If caption includes words suggesting it's a decorative element, reduce priority
        if any(keyword in caption.lower() for keyword in ['icon', 'bullet', 'background', 'decoration']):
            score -= 50

        # Store image with its score
        scored_images.append((score, img))

    # Sort images by score (highest first)
    scored_images.sort(reverse=True, key=lambda x: x[0])

    # Take the top-scoring images
    selected = [img for _, img in scored_images[:max_images]]

    logger.debug(f"Selected {len(selected)} images from {len(images)} available images")
    return selected

def improve_text(text: str, improvement_type: str = "improve") -> str:
    """
    Improve text using OpenAI

    Args:
        text: The text to improve
        improvement_type: Type of improvement (improve, simplify, extend)

    Returns:
        Improved text
    """
    logger.debug(f"Improving text with type: {improvement_type}")

    # If OpenAI is not available, return the original text
    if openai is None:
        logger.warning("OpenAI not available. Returning original text without improvements.")
        return text

    # Create a prompt based on the improvement type
    if improvement_type == "simplify":
        system_prompt = "You are an editor who specializes in simplifying complex language while retaining meaning."
        user_prompt = f"Simplify the following text to make it more accessible while preserving key information:\n\n{text}"
    elif improvement_type == "extend":
        system_prompt = "You are an editor who specializes in expanding content with relevant details."
        user_prompt = f"Expand the following text with more details and context while maintaining the professional tone:\n\n{text}"
    else:  # improve
        system_prompt = "You are an expert editor who improves professional writing."
        user_prompt = f"Improve the following text to make it more professional, impactful, and persuasive:\n\n{text}"

    # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
    # do not change this unless explicitly requested by the user
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Error improving text: {str(e)}")
        # Return original text if there's an error
        logger.info("Returning original text due to error in OpenAI API call")
        return text

def split_text(text, max_tokens=5000):
    """
    Split text into chunks based on maximum token size

    Args:
        text: Text to split
        max_tokens: Maximum tokens per chunk

    Returns:
        List of text chunks
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""
    for p in paragraphs:
        if len(current_chunk) + len(p) < max_tokens:
            current_chunk += p + "\n\n"
        else:
            chunks.append(current_chunk)
            current_chunk = p + "\n\n"
    if current_chunk:
        chunks.append(current_chunk)
    return chunks