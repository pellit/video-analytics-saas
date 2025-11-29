<?php

namespace App\Mail;

use Illuminate\Bus\Queueable;
use Illuminate\Mail\Mailable;
use Illuminate\Queue\SerializesModels;

class MagicLinkMail extends Mailable
{
    use Queueable, SerializesModels;

    public $frontendUrl;

    /**
     * Create a new message instance.
     */
    public function __construct(string $frontendUrl)
    {
        $this->frontendUrl = $frontendUrl;
    }

    /**
     * Build the message.
     */
    public function build()
    {
        return $this->subject('Tu enlace de acceso - Video SaaS')
                    ->view('emails.magiclink')
                    ->with(['url' => $this->frontendUrl]);
    }
}
